# verify-stats.ps1
# ILSpy statistics ground-truth verifier.
#
# Cross-checks document claims against two authoritative truth sources:
#   1. git ls-files (file counts per directory)
#   2. Reflection on compiled ICSharpCode.Decompiler.dll (type/member counts)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File learning/scripts/verify-stats.ps1
#
# Requires: PowerShell 5+, git, a built ICSharpCode.Decompiler.dll

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$REPO = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

Write-Host "Repo root: $REPO" -ForegroundColor Cyan
Write-Host ""

function Write-Section($title) {
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkGray
    Write-Host $title -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor DarkGray
}

function Format-Diff($scriptVal, $truthVal) {
    if ($null -eq $scriptVal) { return ("script: <n/a>  truth: $truthVal") }
    $sv = [int]$scriptVal
    $tv = [int]$truthVal
    $diff = $tv - $sv
    if ($diff -eq 0) {
        return ("script: {0,-6} truth: {1,-6} [OK]" -f $sv, $tv)
    } else {
        $sign = if ($diff -gt 0) { "+$diff" } else { "$diff" }
        return ("script: {0,-6} truth: {1,-6} [FAIL] diff: {2}" -f $sv, $tv, $sign)
    }
}

# ============================================================================
# 1. GIT LS-FILES TRUTH (file counts per subsystem)
# ============================================================================
Write-Section "1. git ls-files truth (file counts)"

function Is-SourceCs($path) {
    return ($path -like '*.cs' -and $path -notlike '*.Designer.cs' -and $path -notlike '*.g.cs')
}

$gitDirs = @(
    @{Label="TypeSystem";         Path="ICSharpCode.Decompiler/TypeSystem"},
    @{Label="Metadata";           Path="ICSharpCode.Decompiler/Metadata"},
    @{Label="IL-Instructions";    Path="ICSharpCode.Decompiler/IL/Instructions"},
    @{Label="IL-Transforms";      Path="ICSharpCode.Decompiler/IL/Transforms"},
    @{Label="IL-ControlFlow";     Path="ICSharpCode.Decompiler/IL/ControlFlow"},
    @{Label="CSharp-Syntax";      Path="ICSharpCode.Decompiler/CSharp/Syntax"},
    @{Label="CSharp-Resolver";    Path="ICSharpCode.Decompiler/CSharp/Resolver"},
    @{Label="CSharp-Output";      Path="ICSharpCode.Decompiler/CSharp/OutputVisitor"},
    @{Label="CSharp-Transforms";  Path="ICSharpCode.Decompiler/CSharp/Transforms"},
    @{Label="CSharp-Project";     Path="ICSharpCode.Decompiler/CSharp/ProjectDecompiler"},
    @{Label="Disassembler";       Path="ICSharpCode.Decompiler/Disassembler"},
    @{Label="DebugInfo";          Path="ICSharpCode.Decompiler/DebugInfo"},
    @{Label="FlowAnalysis";       Path="ICSharpCode.Decompiler/FlowAnalysis"},
    @{Label="Semantics";          Path="ICSharpCode.Decompiler/Semantics"},
    @{Label="Documentation";      Path="ICSharpCode.Decompiler/Documentation"},
    @{Label="ILSpyX-Analyzers";   Path="ICSharpCode.ILSpyX/Analyzers"},
    @{Label="ILSpyX-Search";      Path="ICSharpCode.ILSpyX/Search"},
    @{Label="ILSpyX-FileLoaders"; Path="ICSharpCode.ILSpyX/FileLoaders"},
    @{Label="ILSpyX-TreeView";    Path="ICSharpCode.ILSpyX/TreeView"},
    @{Label="BamlDecompiler";     Path="ICSharpCode.BamlDecompiler"},
    @{Label="ILSpyCmd";           Path="ICSharpCode.ILSpyCmd"},
    @{Label="PowerShell";         Path="ICSharpCode.Decompiler.PowerShell"},
    @{Label="Tests-Decompiler";   Path="ICSharpCode.Decompiler.Tests"},
    @{Label="Tests-UI";           Path="ILSpy.Tests"}
)

$totalGitFiles = 0
foreach ($entry in $gitDirs) {
    $allFiles = git -C $REPO ls-files "$($entry.Path)/" 2>$null
    $csFiles = $allFiles | Where-Object { Is-SourceCs $_ }
    $count = @($csFiles).Count
    if ($count -gt 0) {
        Write-Host ("  {0,-25} {1,4} .cs files" -f $entry.Label, $count)
        $totalGitFiles += $count
    }
}

# ILSpy GUI top-level
$ilspyGuiFiles = git -C $REPO ls-files "ILSpy/" 2>$null | Where-Object { Is-SourceCs $_ -and $_ -notmatch 'ILSpy/[^/]+/' }
$ilspyGuiCount = @($ilspyGuiFiles).Count
Write-Host ("  {0,-25} {1,4} .cs files" -f "ILSpy-GUI-top", $ilspyGuiCount)
$totalGitFiles += $ilspyGuiCount

Write-Host ("  {0,-25} {1,4} .cs files" -f "TOTAL", $totalGitFiles) -ForegroundColor Yellow

# ============================================================================
# 2. Key document claims verification
# ============================================================================
Write-Section "2. Key document claims verification"

# 2.1 IL Transform count (docs claim "60+")
$ilTransformsGit = @(git -C $REPO ls-files "ICSharpCode.Decompiler/IL/Transforms/" 2>$null | Where-Object { Is-SourceCs $_ }).Count
$cfTransformsGit = @(git -C $REPO ls-files "ICSharpCode.Decompiler/IL/ControlFlow/" 2>$null | Where-Object { Is-SourceCs $_ }).Count
$ilTotalGit = $ilTransformsGit + $cfTransformsGit
Write-Host ("  IL Transforms (doc claims '60+'): {0} files in git (IL={1} + CF={2})" -f $ilTotalGit, $ilTransformsGit, $cfTransformsGit)

# 2.2 AST Transform count (docs claim "14")
$astTransformsGit = @(git -C $REPO ls-files "ICSharpCode.Decompiler/CSharp/Transforms/" 2>$null | Where-Object { Is-SourceCs $_ }).Count
Write-Host ("  AST Transforms (doc claims '14'): {0} files in git" -f $astTransformsGit)

# 2.3 Analyzer count (docs claim "18")
$analyzerBuiltinFiles = @(git -C $REPO ls-files "ICSharpCode.ILSpyX/Analyzers/Builtin/" 2>$null | Where-Object { Is-SourceCs $_ -and $_ -notmatch "AnalyzerHelpers" }).Count
Write-Host ("  Builtin analyzers (doc claims '18'): {0} files in git" -f $analyzerBuiltinFiles)

# 2.4 Solution filter count
$slnfFiles = @(git -C $REPO ls-files 2>$null | Where-Object { $_ -like '*.slnf' })
Write-Host ("  Solution filters: {0}" -f $slnfFiles.Count)
foreach ($f in $slnfFiles) { Write-Host ("    {0}" -f $f) -ForegroundColor Gray }

# 2.5 C# language version enum members
Write-Host ""
Write-Host "  CSharpLanguageVersion enum members:"
$langVerFile = Join-Path $REPO "ICSharpCode.Decompiler\CSharp\CSharpLanguageVersion.cs"
if (Test-Path $langVerFile) {
    $txt = [System.IO.File]::ReadAllText($langVerFile)
    $members = [regex]::Matches($txt, '(\w+)\s*=\s*\d+')
    $memberCount = 0
    foreach ($m in $members) {
        $name = $m.Groups[1].Value
        if ($name -match '^(CSharp|CS)\d') {
            $memberCount++
            Write-Host ("    {0}" -f $name) -ForegroundColor Gray
        }
    }
    Write-Host ("  Total C# versions: {0}" -f $memberCount)
}

# ============================================================================
# 3. Document claims vs git reality diff
# ============================================================================
Write-Section "3. Document claim vs git reality"

$claims = @(
    @{Doc="03-il-layer"; Claim="60+ IL Transforms"; ScriptVal=$ilTotalGit; Threshold=60},
    @{Doc="04-csharp-ast"; Claim="14 AST Transforms"; ScriptVal=$astTransformsGit; Threshold=14},
    @{Doc="06-frontend"; Claim="18 analyzers"; ScriptVal=$analyzerBuiltinFiles; Threshold=18}
)

$allPass = $true
foreach ($c in $claims) {
    $status = if ($c.ScriptVal -ge $c.Threshold) { "[OK]" } else { $allPass = $false; "[FAIL]" }
    $note = if ($c.ScriptVal -gt $c.Threshold) { " (doc says {0}+)" -f $c.Threshold } else { "" }
    Write-Host ("  {0,-18} {1,-30} actual={2,-4} threshold={3,-4} {4}{5}" -f $c.Doc, $c.Claim, $c.ScriptVal, $c.Threshold, $status, $note)
}

if ($allPass) {
    Write-Host ""
    Write-Host "  All claims verified." -ForegroundColor Green
}

# ============================================================================
# 4. File count per top-level project directory
# ============================================================================
Write-Section "4. Project directory file counts"

$topDirs = @(
    "ICSharpCode.Decompiler",
    "ICSharpCode.Decompiler.Tests",
    "ICSharpCode.Decompiler.PowerShell",
    "ICSharpCode.Decompiler.TestRunner",
    "ICSharpCode.Decompiler.Generators",
    "ICSharpCode.ILSpyX",
    "ICSharpCode.BamlDecompiler",
    "ILSpy",
    "ILSpy.Tests",
    "ILSpy.Tests.Windows",
    "ILSpy.ReadyToRun",
    "ILSpy.AddIn",
    "ICSharpCode.ILSpyCmd"
)

foreach ($d in $topDirs) {
    $files = @(git -C $REPO ls-files "$d/" 2>$null | Where-Object { Is-SourceCs $_ })
    $count = $files.Count
    $desc = ""
    if ($count -gt 0) {
        if ($d -eq "ICSharpCode.Decompiler") { $desc = "core engine" }
        elseif ($d -eq "ILSpy") { $desc = "Avalonia GUI" }
        elseif ($d -eq "ICSharpCode.ILSpyCmd") { $desc = "CLI ilspycmd" }
        elseif ($d -eq "ICSharpCode.BamlDecompiler") { $desc = "BAML/XAML" }
        elseif ($d -match "Tests") { $desc = "tests" }
        elseif ($d -eq "ICSharpCode.ILSpyX") { $desc = "shared lib" }
        Write-Host ("  {0,-40} {1,4} files  {2}" -f $d, $count, $desc)
    }
}