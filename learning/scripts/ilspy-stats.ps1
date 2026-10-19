# ILSpy source stats - for deciding document structure
# Usage: powershell -ExecutionPolicy Bypass -File learning/scripts/ilspy-stats.ps1

$REPO = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$subsystems = @(
    @{Name="TypeSystem";      Path="ICSharpCode.Decompiler\TypeSystem";         Group="Meta"},
    @{Name="Metadata";        Path="ICSharpCode.Decompiler\Metadata";            Group="Meta"},
    @{Name="IL-Instructions"; Path="ICSharpCode.Decompiler\IL\Instructions";     Group="IL"},
    @{Name="IL-Transforms";   Path="ICSharpCode.Decompiler\IL\Transforms";       Group="IL"},
    @{Name="IL-ControlFlow";  Path="ICSharpCode.Decompiler\IL\ControlFlow";      Group="IL"},
    @{Name="IL-Core";         Path="ICSharpCode.Decompiler\IL";                  Group="IL"},
    @{Name="CSharp-Syntax";   Path="ICSharpCode.Decompiler\CSharp\Syntax";       Group="CSharp"},
    @{Name="CSharp-Resolver"; Path="ICSharpCode.Decompiler\CSharp\Resolver";     Group="CSharp"},
    @{Name="CSharp-Output";   Path="ICSharpCode.Decompiler\CSharp\OutputVisitor";Group="CSharp"},
    @{Name="CSharp-Transforms";Path="ICSharpCode.Decompiler\CSharp\Transforms"; Group="CSharp"},
    @{Name="CSharp-Project";  Path="ICSharpCode.Decompiler\CSharp\ProjectDecompiler";Group="CSharp"},
    @{Name="CSharp-Core";     Path="ICSharpCode.Decompiler\CSharp";              Group="CSharp"},
    @{Name="Disassembler";    Path="ICSharpCode.Decompiler\Disassembler";        Group="Other"},
    @{Name="DebugInfo";       Path="ICSharpCode.Decompiler\DebugInfo";           Group="Other"},
    @{Name="FlowAnalysis";    Path="ICSharpCode.Decompiler\FlowAnalysis";        Group="Other"},
    @{Name="Semantics";       Path="ICSharpCode.Decompiler\Semantics";           Group="Other"},
    @{Name="Documentation";   Path="ICSharpCode.Decompiler\Documentation";       Group="Other"},
    @{Name="Solution";        Path="ICSharpCode.Decompiler\Solution";            Group="Other"},
    @{Name="DebugSteps";      Path="ICSharpCode.Decompiler\DebugSteps";          Group="Other"},
    @{Name="ILSpyX-Analyzers";Path="ICSharpCode.ILSpyX\Analyzers";              Group="ILSpyX"},
    @{Name="ILSpyX-Search";   Path="ICSharpCode.ILSpyX\Search";                  Group="ILSpyX"},
    @{Name="ILSpyX-Loaders";  Path="ICSharpCode.ILSpyX\FileLoaders";            Group="ILSpyX"},
    @{Name="ILSpyX-TreeView"; Path="ICSharpCode.ILSpyX\TreeView";                Group="ILSpyX"},
    @{Name="ILSpyX-Core";     Path="ICSharpCode.ILSpyX";                         Group="ILSpyX"},
    @{Name="BamlDecompiler";  Path="ICSharpCode.BamlDecompiler";                 Group="Baml"},
    @{Name="ILSpy-GUI";       Path="ILSpy";                                      Group="Frontend"},
    @{Name="ILSpyCmd";        Path="ICSharpCode.ILSpyCmd";                       Group="CLI"},
    @{Name="PowerShell";      Path="ICSharpCode.Decompiler.PowerShell";          Group="CLI"},
    @{Name="Tests-Decompiler";Path="ICSharpCode.Decompiler.Tests";               Group="Tests"},
    @{Name="Tests-GUI";       Path="ILSpy.Tests";                                Group="Tests"},
    @{Name="Decompiler-Root"; Path="ICSharpCode.Decompiler";                     Group="Other"}
)

Write-Host "ILSpy Source Code Statistics" -ForegroundColor Cyan
Write-Host "Repo: $REPO" -ForegroundColor Gray
Write-Host ""

$groupSummary = @{}
$totalFiles = 0
$totalLines = 0

foreach ($sub in $subsystems) {
    $dir = Join-Path $REPO $sub.Path
    if (-not (Test-Path $dir)) { continue }
    $csFiles = Get-ChildItem -Path $dir -Filter *.cs -File -ErrorAction SilentlyContinue | 
        Where-Object { $_.FullName -notmatch '\\(bin|obj)\\' -and $_.Name -notlike "*.g.cs" -and $_.Name -notlike "*.Designer.cs" }
    $fileCount = $csFiles.Count
    if ($fileCount -eq 0) { continue }
    $lines = 0
    foreach ($f in $csFiles) {
        $lines += (Get-Content $f.FullName | Measure-Object -Line).Lines
    }
    $group = $sub.Group
    if (-not $groupSummary[$group]) {
        $groupSummary[$group] = @{Files=0; Lines=0}
    }
    $groupSummary[$group].Files += $fileCount
    $groupSummary[$group].Lines += $lines
    $totalFiles += $fileCount
    $totalLines += $lines
}

Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host "Subsystem breakdown (.cs only, no generated/bin/obj)" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host ""

$groupOrder = @("Meta", "IL", "CSharp", "ILSpyX", "Frontend", "CLI", "Tests", "Baml", "Other")
$groupLabels = @{
    Meta     = "Metadata + TypeSystem (file loading, type hierarchy)"
    IL       = "IL Layer (ILAst, 60+ transforms, control flow)"
    CSharp   = "C# Layer (AST, Resolver, 14 transforms, Output)"
    ILSpyX   = "Shared (Analyzers, Search, FileLoaders, TreeView)"
    Frontend = "Avalonia GUI"
    CLI      = "ilspycmd + PowerShell"
    Tests    = "Test suites"
    Baml     = "BAML/XAML decompiler"
    Other    = "Other (FlowAnalysis, DebugInfo, Disassembler...)"
}

foreach ($group in $groupOrder) {
    $s = $groupSummary[$group]
    if ($s -and $s.Files -gt 0) {
        $pct = [math]::Round(($s.Lines / $totalLines) * 100, 1)
        $label = $groupLabels[$group]
        Write-Host ("  {0,-12} {1,5} files, {2,8:N0} LOC ({3,5}%)  | {4}" -f $group, $s.Files, $s.Lines, $pct, $label)
    }
}
Write-Host ""
Write-Host ("  TOTAL: {0} files, {1:N0} LOC" -f $totalFiles, $totalLines) -ForegroundColor Yellow
Write-Host ""

# Document coverage mapping
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host "Document -> Subsystem coverage" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host ""

$docMap = @(
    @{Doc="02-metadata";     Covers=@("Meta")},
    @{Doc="03-il-layer";     Covers=@("IL")},
    @{Doc="04-csharp-ast";   Covers=@("CSharp")},
    @{Doc="05-pipeline";     Covers=@("Meta","IL","CSharp","Other")},
    @{Doc="06-frontend";     Covers=@("Frontend","ILSpyX")},
    @{Doc="07-cli";          Covers=@("CLI","Baml")}
)

foreach ($d in $docMap) {
    $totalCovered = 0
    foreach ($c in $d.Covers) {
        $s = $groupSummary[$c]
        if ($s) { $totalCovered += $s.Lines }
    }
    $pct = [math]::Round(($totalCovered / $totalLines) * 100, 1)
    Write-Host ("  {0}  covers {1,8:N0} LOC ({2,5}%)" -f $d.Doc, $totalCovered, $pct)
}

# Document stats
$docFiles = Get-ChildItem -Path (Join-Path $REPO "learning") -Filter "*.md" -File
$docLines = 0
foreach ($f in $docFiles) { $docLines += (Get-Content $f.FullName | Measure-Object -Line).Lines }
$avgDocLines = [math]::Round($docLines / $docFiles.Count)

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host "Document metrics" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host ("  Documents:      {0}" -f $docFiles.Count)
Write-Host ("  Doc total LOC:  {0:N0}" -f $docLines)
Write-Host ("  Avg doc size:   {0:N0} lines" -f $avgDocLines)
Write-Host ("  Source LOC:     {0:N0}" -f $totalLines)
Write-Host ("  Doc:Source ratio 1:{0:N0}" -f [math]::Round($totalLines / $docLines, 0))

# Missing coverage
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host "Potentially MISSING coverage" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor DarkGray
$allCoveredGroups = @("Meta","IL","CSharp","Other","Frontend","ILSpyX","CLI","Baml")
$missingGroups = @()
foreach ($group in $groupOrder) {
    if ($group -eq "Tests") { continue }
    $s = $groupSummary[$group]
    if ($s -and $s.Lines -gt 500 -and $group -notin $allCoveredGroups) {
        $missingGroups += $group
    }
}
if ($missingGroups.Count -eq 0) {
    Write-Host "  All major subsystems covered." -ForegroundColor Green
} else {
    foreach ($g in $missingGroups) {
        $s = $groupSummary[$g]
        Write-Host ("  {0}: {1} files, {2:N0} LOC" -f $g, $s.Files, $s.Lines) -ForegroundColor Yellow
    }
}