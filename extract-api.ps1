#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Use ilspycmd to decompile a .NET assembly and extract its public API surface.
.DESCRIPTION
    Decompiles the assembly with ilspycmd, then parses the generated C# files to
    collect every public type (class, interface, struct, enum, delegate, record)
    and its public members (methods, properties, fields, events, constructors).
    Outputs a clean, readable API listing grouped by namespace+type.
.PARAMETER AssemblyPath
    Path to the .dll or .exe to analyze.
.PARAMETER OutputDir
    Where to write the decompiled sources and the API listing.
    Defaults to a 'decompiled_api' folder next to the assembly.
.PARAMETER ApiFile
    Path for the final API listing file.
    Defaults to '<AssemblyName>.api.txt' inside OutputDir.
.EXAMPLE
    .\extract-api.ps1 "C:\libs\ScottPlot.dll"
.EXAMPLE
    .\extract-api.ps1 "C:\libs\ScottPlot.dll" -OutputDir "C:\api-dump" -ApiFile "api.txt"
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateScript({ Test-Path $_ })]
    [string]$AssemblyPath,

    [string]$OutputDir,

    [string]$ApiFile
)

$ErrorActionPreference = 'Stop'

$assemblyName = [System.IO.Path]::GetFileNameWithoutExtension($AssemblyPath)

if (-not $OutputDir) {
    $OutputDir = Join-Path (Split-Path $AssemblyPath -Parent) "${assemblyName}_api"
}
if (-not $ApiFile) {
    $ApiFile = Join-Path $OutputDir "$assemblyName.api.txt"
}

Write-Host "=== Extract Public API Surface ===" -ForegroundColor Cyan
Write-Host "  Assembly : $AssemblyPath"
Write-Host "  Work dir : $OutputDir"
Write-Host "  API file : $ApiFile"

# -------------------------------------------------------------------
# Step 1: Decompile with ilspycmd
# -------------------------------------------------------------------
Write-Host "`n[1/3] Decompiling with ilspycmd..." -ForegroundColor Yellow

$decompiledDir = Join-Path $OutputDir "src"
if (Test-Path $decompiledDir) {
    Remove-Item $decompiledDir -Recurse -Force
}

$ilspyArgs = @(
    '-p',
    '-o', $decompiledDir,
    '--nested-directories',
    $AssemblyPath
)

& ilspycmd @ilspyArgs 2>&1 | ForEach-Object {
    if ($_ -match '^(Error|Warning)') { Write-Host $_ -ForegroundColor Red }
}

if (-not (Test-Path $decompiledDir)) {
    Write-Error "Decompilation failed: no output directory created."
    exit 1
}

$csFiles = Get-ChildItem $decompiledDir -Recurse -Filter *.cs
Write-Host "  Decompiled $($csFiles.Count) .cs files." -ForegroundColor Green

# -------------------------------------------------------------------
# Step 2: Parse public declarations
# -------------------------------------------------------------------
Write-Host "`n[2/3] Parsing public API declarations..." -ForegroundColor Yellow

# Regex patterns for C# declarations in decompiled output.
# Key insight: decompiled code is well-formatted, with 'public' keyword
# at predictable positions.

$typePatterns = @(
    @{ Pattern = '^\s*public\s+(static\s+)?class\s+(\w+)';        Kind = 'class'      },
    @{ Pattern = '^\s*public\s+(static\s+)?interface\s+(\w+)';    Kind = 'interface'  },
    @{ Pattern = '^\s*public\s+(readonly\s+)?struct\s+(\w+)';     Kind = 'struct'     },
    @{ Pattern = '^\s*public\s+enum\s+(\w+)';                     Kind = 'enum'       },
    @{ Pattern = '^\s*public\s+delegate\s+';                      Kind = 'delegate'   },
    @{ Pattern = '^\s*public\s+(sealed\s+)?record\s+(\w+)';       Kind = 'record'     }
)

# We collect results as:
#   $api = @{ 'Namespace' = @{ 'TypeName' = @{ Kind='class'; Members=@('method void Dispose()', ...) } } }
$api = [ordered]@{}

$currentNamespace = ''
$currentType = ''
$currentTypeKind = ''
$depth = 0          # brace depth, 1 = inside a type
$headerLines = 0    # skip file header (copyright block)

foreach ($file in $csFiles) {
    $currentNamespace = ''
    $currentType = ''
    $currentTypeKind = ''
    $depth = 0
    $lines = Get-Content $file.FullName -Encoding UTF8
    $headerLines = 0
    $inHeader = $true

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        # Skip copyright header
        if ($inHeader) {
            if ($line -match '^(//|#region|#endregion|\s*$)') {
                $headerLines++
                continue
            }
            $inHeader = $false
        }

        # Skip using directives, attributes, blank lines, XML comments
        if ($line -match '^\s*using\s' -or
            $line -match '^\s*\[\s*[\w.]+' -or
            $line -match '^\s*$' -or
            $line -match '^\s*///') {
            continue
        }

        # Track namespace
        if ($line -match '^namespace\s+([\w.]+)') {
            $currentNamespace = $Matches[1]
            if (-not $api.Contains($currentNamespace)) {
                $api[$currentNamespace] = [ordered]@{}
            }
            continue
        }

        # Detect public type declarations
        if ($depth -eq 0) {
            foreach ($tp in $typePatterns) {
                if ($line -match $tp.Pattern) {
                    $typeName = if ($Matches.Count -ge 3) { $Matches[3] } else { $Matches[2] }
                    if (-not $typeName) {
                        # delegate: parse name from the line
                        if ($line -match 'delegate\s+\S+\s+(\w+)\(') {
                            $typeName = $Matches[1]
                        } elseif ($line -match 'delegate\s+\S+\s+(\w+);') {
                            $typeName = $Matches[1]
                        }
                    }
                    if ($typeName) {
                        $currentType = $typeName
                        $currentTypeKind = $tp.Kind
                        if (-not $api[$currentNamespace].Contains($currentType)) {
                            $api[$currentNamespace][$currentType] = @{
                                Kind    = $currentTypeKind
                                Members = [System.Collections.Generic.List[string]]::new()
                            }
                        }
                    }
                    break
                }
            }
        }

        # Track brace depth
        $openCount  = ($line.ToCharArray() | Where-Object { $_ -eq '{' }).Count
        $closeCount = ($line.ToCharArray() | Where-Object { $_ -eq '}' }).Count
        $depth += $openCount - $closeCount

        # Inside a public type (depth == 1): collect public members
        if ($depth -eq 1 -and $currentType -ne '' -and $line -match '^\s*public\s') {
            # Clean up the line: strip leading whitespace, trailing {, normalize spaces
            $member = $line -replace '^\s+', ''
            $member = $member -replace '\s*\{\s*$', ''
            $member = $member -replace '\s+', ' '
            $member = $member.Trim()

            # Skip certain non-member patterns
            if ($member -match '^public (class|interface|struct|enum|record|delegate|const)\s' -or
                $member -match '^public\s*$') {
                # nested type or incomplete line - skip
            } else {
                # Handle multi-line signatures (e.g. attributes on next line already skipped)
                $api[$currentNamespace][$currentType].Members.Add($member)
            }
        }
    }
}

# -------------------------------------------------------------------
# Step 3: Write API listing
# -------------------------------------------------------------------
Write-Host "`n[3/3] Writing API listing..." -ForegroundColor Yellow

$totalTypes = 0
$totalMembers = 0

$sb = [System.Text.StringBuilder]::new()
[void]$sb.AppendLine("Public API Surface: $assemblyName")
[void]$sb.AppendLine("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
[void]$sb.AppendLine("Assembly: $AssemblyPath")
[void]$sb.AppendLine("".PadRight(80, '='))

foreach ($ns in $api.Keys) {
    $types = $api[$ns]
    if ($types.Count -eq 0) { continue }

    [void]$sb.AppendLine()
    [void]$sb.AppendLine("namespace $ns")
    [void]$sb.AppendLine("".PadRight(80, '-'))

    foreach ($typeName in $types.Keys) {
        $t = $types[$typeName]
        [void]$sb.AppendLine()
        [void]$sb.AppendLine("  $($t.Kind) $typeName")
        $totalTypes++

        foreach ($m in $t.Members) {
            [void]$sb.AppendLine("    $m")
            $totalMembers++
        }
    }
}

[void]$sb.AppendLine()
[void]$sb.AppendLine("".PadRight(80, '='))
[void]$sb.AppendLine("Total: $totalTypes public types, $totalMembers public members")

$sb.ToString() | Out-File -FilePath $ApiFile -Encoding UTF8

Write-Host "  Types   : $totalTypes" -ForegroundColor Green
Write-Host "  Members : $totalMembers" -ForegroundColor Green
Write-Host "  Output  : $ApiFile" -ForegroundColor Green
Write-Host "`nDone." -ForegroundColor Cyan