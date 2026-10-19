# ILSpy 新手入门

> 职责：新手唯一入口 — 架构速览 + 5 分钟上手 + 搭建环境
跨平台 .NET 程序集浏览器 / 反编译器 · Avalonia 12 · 2026-10-19

---

## 一、这是什么？

ILSpy 是一个跨平台 .NET 程序集浏览器和反编译器。核心哲学：**将编译后的 .NET 程序集（DLL/EXE）还原为可读的 C# 源代码**。

```bash
# 最简用法：反编译一个程序集
ilspycmd MyAssembly.dll -o ./output

# 或启动 GUI 浏览器
ilspy
```

ILSpy 支持：
- **反编译**：IL 字节码 → 高质量 C# 代码（含 async/await、LINQ、yield return 等高级模式识别）
- **浏览**：程序集树形导航，查看类型、方法、字段、属性
- **IL 查看**：原始 IL 指令、ILASt 中间表示
- **分析**：引用分析（谁调用了谁、类型被谁使用等）
- **导出**：整项目反编译导出为 .csproj 解决方案
- **调试**：Debug Steps 逐步查看反编译中间状态

---

## 二、30 秒理解架构

```
┌──────────────────────────────────────────────────────────────┐
│                     ILSpy 分层架构                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Frontend    Avalonia UI · CLI (ilspycmd) · PowerShell       │
│    ↑         MEF 插件系统                                     │
│                                                              │
│  ILSpyX      文件加载器 · 分析器 · 搜索 · TreeView 抽象        │
│    ↑                                                         │
│                                                              │
│  Decompiler ┌─────────────────────────────────────────────┐  │
│  Engine     │  CSharpDecompiler (主入口)                    │  │
│             │    C# AST Transforms (14 步)                  │  │
│             │    ↑                                          │  │
│             │  StatementBuilder / ExpressionBuilder         │  │
│             │    ↑                                          │  │
│             │  IL Transform Pipeline (60+ 步)               │  │
│             │    ↑                                          │  │
│             │  ILReader (IL 字节码 → ILAst)                 │  │
│             │    ↑                                          │  │
│             │  类型系统 (IType/IMethod/IField...)            │  │
│             └─────────────────────────────────────────────┘  │
│    ↑                                                         │
│  Metadata   PEFile · MetadataFile · AssemblyResolver         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

你只需关心两个入口：
- **`CSharpDecompiler`** — 编程 API 反编译（库消费者）
- **`ilspycmd` / ILSpy GUI** — 命令行 / 图形界面（终端用户）

**五条核心链路**：

| 链路 | 路径 | 详析 |
|---|---|---|
| 元数据 | 文件 → PEFile → MetadataFile → DecompilerTypeSystem | [02](02-metadata-type-system.md) |
| IL → ILAst | ILReader.ReadIL() → ILFunction → IL Transforms | [03](03-il-layer.md) |
| ILAst → C# | StatementBuilder → C# SyntaxTree → AST Transforms | [04](04-csharp-ast.md) |
| C# → 文本 | CSharpOutputVisitor → TextWriterTokenWriter | [04](04-csharp-ast.md) |
| 完整管道 | CSharpDecompiler.DecompileWholeTypeAsString() | [05](05-decompiler-pipeline.md) |

---

## 三、核心概念

### 3.1 反编译管道的三个阶段

ILSpy 的反编译不是一步到位的，而是经过三层表示：

```
原始 IL 字节码 (Raw Bytes)
    ↓ ILReader
ILAst (IL 指令的 AST 表示 — ILFunction / Block / StLoc)
    ↓ IL Transforms (60+ 步：内联、循环检测、async 识别...)
优化后的 ILAst
    ↓ StatementBuilder + ExpressionBuilder
C# AST (CSharpDecompiler 自定义语法树 — MethodDeclaration / BlockStatement)
    ↓ AST Transforms (14 步：声明变量、命名冲突修复、XML 文档...)
优化后的 C# AST
    ↓ CSharpOutputVisitor
C# 源代码文本
```

### 3.2 类型系统 (Type System) — 最核心的抽象

ILSpy 不直接使用 `System.Reflection`，而是构建了自己的类型系统接口层：

```csharp
// 类型系统核心接口
interface IType { FullName, TypeParameterCount, ... }
interface ITypeDefinition : IType { ... }
interface IMethod : IMember { Parameters, ReturnType, ... }
interface IField : IMember { Type, IsReadOnly, ... }
interface IProperty : IMember { Getter, Setter, ... }
interface IEvent : IMember { AddAccessor, RemoveAccessor, ... }
```

> 详见 [02-metadata-type-system.md](02-metadata-type-system.md)

### 3.3 ILAst — IL 的抽象语法树

IL 字节码在 ILSpy 中被表示为树结构的 ILAst：

```csharp
// ILAst 指令示例
class StLoc(ILVariable variable, ILInstruction value) : ILInstruction
class CallInstruction(IMethod method, ...) : ILInstruction
class IfInstruction(ILInstruction condition, Block trueBlock, ...) : ILInstruction
class BlockContainer(Block entryPoint) : ILInstruction  // 函数体
```

> 详见 [03-il-layer.md](03-il-layer.md)

### 3.4 C# AST — 反编译结果的语法树

C# 源码被表示为自定义的语法树（非 Roslyn SyntaxTree）：

```
SyntaxTree
  └── NamespaceDeclaration
        └── TypeDeclaration (class/struct/interface/enum)
              ├── MethodDeclaration
              │     └── BlockStatement
              │           ├── VariableDeclarationStatement
              │           └── ExpressionStatement
              ├── PropertyDeclaration
              └── FieldDeclaration
```

> 详见 [04-csharp-ast.md](04-csharp-ast.md)

---

## 四、5 分钟上手

### 4.1 安装命令行工具

```powershell
dotnet tool install --global ilspycmd
```

### 4.2 第一个反编译

```powershell
# 反编译单个方法
ilspycmd System.Linq.dll -m "Enumerable.Where"

# 反编译整个程序集到目录
ilspycmd MyAssembly.dll -o ./decompiled

# 查看原始 IL
ilspycmd MyAssembly.dll -m "MyClass.MyMethod" --il
```

### 4.3 编程 API 反编译

```csharp
using ICSharpCode.Decompiler;
using ICSharpCode.Decompiler.CSharp;

var settings = new DecompilerSettings(LanguageVersion.Latest);
var decompiler = new CSharpDecompiler("MyAssembly.dll", settings);

// 反编译整个类型
string code = decompiler.DecompileWholeTypeAsString(
    new FullTypeName("MyNamespace.MyClass"));

// 反编译单个方法
string methodCode = decompiler.DecompileAsString(
    methodHandle);

Console.WriteLine(code);
```

### 4.4 启动 GUI

```powershell
dotnet run --project ILSpy/ILSpy.csproj
```

### 4.5 常用 GUI 操作

| 操作 | 效果 |
|---|---|
| Ctrl+O | 打开程序集 |
| Ctrl+T | 搜索类型 |
| F12 / 双击 | 跳转到定义 |
| 右键 → Analyze | 查看引用/被引用 |
| Ctrl+Shift+S | 导出项目 |
| F5 | 切换 IL/C#/ILAst 视图 |
| Debug → Steps | 逐步查看反编译中间状态 |

---

## 五、新手高频陷阱（5 条速览）

1. **`DecompilerSettings` 影响反编译结果** — 不同的 LanguageVersion 会显著影响输出（如是否识别 nint、init 访问器等），在比较输出前确认 settings 一致。
2. **`CSharpDecompiler` 不线程安全** — 每个线程需要自己的实例。
3. **`PEFile` 需要 Dispose** — 它持有文件句柄，不释放会导致文件锁定。
4. **测试需要子模块** — `ILSpy-tests/` 是 git submodule，默认不检出；`git submodule update --init` 后才能运行全部测试。
5. **恢复依赖用 `restore.ps1`，不要直接用 `dotnet restore`** — 否则会裁剪 `packages.lock.json`。

> 全部陷阱：见 [08-usage-caveats.md](08-usage-caveats.md)。

---

## 六、搭建开发环境

**前置条件**：.NET SDK 10.0+。

```powershell
git clone https://github.com/icsharpcode/ILSpy.git
cd ILSpy
git submodule update --init   # 拉取测试子模块（可选，体积大）

# 恢复依赖（必须用脚本，不能用 dotnet restore！）
.\restore.ps1

# 构建
.\build.ps1 -Configuration Debug

# 运行测试（带 TRX 报告）
dotnet test --solution ILSpy.sln --report-trx

# 启动 GUI
dotnet run --project ILSpy/ILSpy.csproj
```

**解决方案说明**：

| 文件 | 内容 |
|---|---|
| `ILSpy.sln` | 完整解决方案（所有项目） |
| `ILSpy.XPlat.slnf` | 跨平台核心：反编译器库 + CLI + 测试（Linux CI 用） |
| `ILSpy.Desktop.slnf` | 桌面 UI：Avalonia + 依赖 + 测试 |

**常见问题**：

| 问题 | 解决 |
|---|---|
| `packages.lock.json` 被修改 | 使用了 `dotnet restore`，改为 `.\restore.ps1`；已修改则 `git checkout -- <path>` |
| 测试跳过（Assert.Ignore） | `ILSpy-tests/` 子模块未初始化，运行 `git submodule update --init` |
| Linux 换行符问题 | 不要运行 `unix2dos`；repo 设置 `* text=auto`，commit 时自动标准化 |

---

## 七、10 分钟实战演练

### 7.1 反编译并分析一个 DLL

```powershell
# 克隆并构建 ILSpy
git clone https://github.com/icsharpcode/ILSpy.git && cd ILSpy
.\restore.ps1 && .\build.ps1 -Configuration Debug

# 用 ilspycmd 反编译 System.Linq.dll
dotnet run --project ICSharpCode.ILSpyCmd/ICSharpCode.ILSpyCmd.csproj -- \
    --ilspycmd \
    "$env:ProgramFiles/dotnet/shared/Microsoft.NETCore.App/10.0.0/System.Linq.dll" \
    -m "Enumerable.Where" \
    -o ./output
```

### 7.2 用编程 API 写一个分析工具

```csharp
// AnalyzeTool.csproj 需要引用 ICSharpCode.Decompiler NuGet 包
using ICSharpCode.Decompiler;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.Metadata;
using ICSharpCode.Decompiler.TypeSystem;

var settings = new DecompilerSettings();
var file = new PEFile("MyAssembly.dll", 
    new FileStream("MyAssembly.dll", FileMode.Open),
    PEStreamOptions.PrefetchEntireImage);
var resolver = new UniversalAssemblyResolver(
    "MyAssembly.dll", throwOnError: false, 
    file.Reader.TargetFrameworkId);

var typeSystem = new DecompilerTypeSystem(file, resolver, settings);
var decompiler = new CSharpDecompiler(typeSystem, settings);

// 遍历所有类型
foreach (var typeDef in typeSystem.MainModule.TypeDefinitions)
{
    if (typeDef.Accessibility == Accessibility.Public)
    {
        Console.WriteLine($"Type: {typeDef.FullName}");
        foreach (var method in typeDef.Methods)
        {
            Console.WriteLine($"  Method: {method.Name}({string.Join(", ", method.Parameters.Select(p => p.Type.FullName))})");
        }
    }
}
```

---

## 八、阅读指南

| 如果你想... | 先读这里 |
|---|---|
| 修改反编译器（修复 bug、添加特性） | 02 → 03 → 04 → 05 |
| 修改 GUI | 06 |
| 添加新的分析器 | 06 |
| 添加新的文件格式支持 | 02 |
| 修改 CLI 工具 | 07 |
| 写测试 | [ICSharpCode.Decompiler.Tests/AGENTS.md](../ICSharpCode.Decompiler.Tests/AGENTS.md) |

---

## 实战参考

- [CONTRIBUTING.md](../CONTRIBUTING.md) — 贡献指南
- [AGENTS.md](../AGENTS.md) — AI Agent 编码指南
- [ICSharpCode.Decompiler.Tests/AGENTS.md](../ICSharpCode.Decompiler.Tests/AGENTS.md) — 测试编写指南