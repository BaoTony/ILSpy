# ILSpy 项目结构导航

> 职责：源码地图 — 解决方案全景 + 核心库目录速查
深度分析见各分层文档（02-10）· 2026-10-19

---

## 一、解决方案全景

```
Solution 'ILSpy.sln' (完整版)
├── ICSharpCode.Decompiler           → 反编译器核心库（核心引擎）
├── ICSharpCode.Decompiler.Tests     → 反编译器测试套件（800+ 测试）
├── ICSharpCode.Decompiler.TestRunner→ 测试外进程运行器
├── ICSharpCode.Decompiler.PowerShell→ PowerShell Cmdlet
├── ICSharpCode.Decompiler.Generators→ 源码生成器（Settings / SyntaxTree）
├── ICSharpCode.ILSpyX               → 跨平台共享库（UI 无关）
├── ICSharpCode.BamlDecompiler       → BAML/XAML 反编译器
├── ILSpy                            → Avalonia 12 GUI 前端
├── ILSpy.Tests                      → Avalonia Headless UI 测试
├── ILSpy.Tests.Windows              → Windows 专用 UI 测试
├── ILSpy.ReadyToRun                 → ReadyToRun 查看器插件
├── ILSpy.AddIn / ILSpy.AddIn.VS2022 → VS 扩展（net472）
├── ICSharpCode.ILSpyCmd             → CLI 命令行前端（ilspycmd）
├── TestPlugin                       → 测试插件
├── TestFixtures.Resources           → 测试夹具资源生成器
├── TestTools/                        → 手工工具（不参与 CI）
│     ├── nugetfuzz                  → 大规模 NuGet 包崩溃扫描
│     └── decompdiff                 → 两版反编译器输出 diff
└── ILSpy.Installer                  → WiX 安装包（net472）
```

| 解决方案筛选器 | 内容 | 用途 |
|---|---|---|
| `ILSpy.Desktop.slnf` | UI + 依赖 + 测试 | 桌面开发首选 |
| `ILSpy.XPlat.slnf` | 反编译器库 + CLI + 测试 | Linux CI / 纯命令行 |
| `ILSpy.Installer.sln` | 安装器相关项目 | 打包发布 |

---

## 二、核心库 `ICSharpCode.Decompiler/` 内部结构

反编译器引擎的核心代码库，多目标框架，跨平台。

### 2.1 顶层目录速查

| 目录 | 定位 | 详见 |
|---|---|---|
| TypeSystem/ | 类型系统抽象（IType/IMethod/IField...） | [02](02-metadata-type-system.md) |
| Metadata/ | PE/Metadata 加载、解析、AssemblyResolver | [02](02-metadata-type-system.md) |
| IL/ | IL 抽象语法树 + IL Transform 管道（60+ 步） | [03](03-il-reader-ast.md) [04](04-il-transforms.md) |
| CSharp/ | C# 语言层：AST、Builder、OutputVisitor、Resolver | [05](05-csharp-syntax-tree.md) [06](06-csharp-output.md) |
| Semantics/ | 语义解析结果（ResolveResult 体系） | [06](06-csharp-output.md) |
| Disassembler/ | IL 反汇编器（ReflectionDisassembler） | — |
| DebugInfo/ | PDB 调试信息生成与消费 | — |
| DebugSteps/ | 逐步调试支持（Stepper） | — |
| Documentation/ | XML 文档注释支持 | — |
| FlowAnalysis/ | 数据流分析（定值分析、支配树） | — |
| Solution/ | 解决方案/项目文件生成 | — |

### 2.2 根目录关键文件

| 文件 | 职责 |
|---|---|
| `CSharp/CSharpDecompiler.cs` | **主入口**：反编译调度器（IL→C# 完整管道） |
| `CSharp/CSharpLanguageVersion.cs` | C# 语言版本枚举（CSharp1 ~ Latest） |
| `DecompilerSettings.cs` | 反编译设置（partial class，含生成部分） |
| `DecompileRun.cs` | 单次反编译运行上下文 |
| `DecompilerException.cs` | 反编译异常 |

### 2.3 IL Layer 详细地图

```
IL/
├── ILReader.cs              ★ IL 字节码 → ILAst（栈模拟 + 控制流图构建）
├── ILInstruction.cs         ★ 所有 IL 指令的基类
├── ILFunction.cs            函数级 ILAst（局部变量 + 异常表 + 调试信息）
├── ILVariable.cs            局部变量
├── BlockBuilder.cs          块构建辅助（Block / BlockContainer）
├── ILAstWritingOptions.cs   输出格式选项
├── ILAmbience.cs            IL 显示名称
├── SlotInfo.cs              栈槽信息
├── StackType.cs             栈类型枚举
│
├── Instructions/            具体的 IL 指令类（~40 个）
│   ├── Block.cs             ★ 基本块
│   ├── BlockContainer.cs    ★ 函数体容器（EntryPoint → Block）
│   ├── StLoc.cs             局部变量存储
│   ├── CallInstruction.cs   方法调用
│   ├── IfInstruction.cs     条件分支
│   ├── SwitchInstruction.cs 多路分支
│   ├── TryInstruction.cs    try/catch/finally
│   ├── LockInstruction.cs   lock 语句
│   ├── UsingInstruction.cs  using 语句
│   └── ...                  其余指令类
│
├── Transforms/              IL Transform 管道（60+ 步）
│   ├── IILTransform.cs      ★ Transform 接口
│   ├── ILInlining.cs        内联
│   ├── SplitVariables.cs    变量拆分
│   ├── CopyPropagation.cs   拷贝传播
│   ├── LoopDetection.cs     循环检测
│   ├── ConditionDetection.cs条件检测（if/else/switch）
│   ├── ExpressionTransforms.cs 表达式级变换
│   ├── StatementTransform.cs   语句级变换（内联/赋值/空合并/可空提升...）
│   └── ...
│
└── ControlFlow/             控制流分析
    ├── ControlFlowGraph.cs  ★ 控制流图
    ├── AsyncAwaitDecompiler.cs  async/await 反编译
    ├── YieldReturnDecompiler.cs yield return 反编译
    ├── SwitchDetection.cs    switch 检测
    └── ...
```

---

## 三、C# 语言层 `ICSharpCode.Decompiler/CSharp/` 详细地图

```
CSharp/
├── CSharpDecompiler.cs      ★ 反编译器主类（编排整个管道）
├── StatementBuilder.cs       ★ ILAst → C# Statement（ILVisitor 模式）
├── ExpressionBuilder.cs      ★ IL 指令 → C# Expression（核心转换逻辑）
├── CallBuilder.cs            方法调用构建
├── TranslationContext.cs     翻译上下文
├── RecordDecompiler.cs       record 类型识别
├── AutoEventDecompiler.cs    自动事件识别
├── Disambiguator.cs          歧义消解
│
├── Syntax/                    C# 抽象语法树定义
│   ├── AstNode.cs            ★ 所有 AST 节点的基类
│   ├── SyntaxTree.cs         语法树根节点
│   ├── AstType.cs            类型引用 AST 节点
│   │
│   ├── TypeMembers/          类型成员：MethodDeclaration/PropertyDeclaration 等
│   ├── Statements/           语句：BlockStatement/IfElseStatement/SwitchStatement 等
│   ├── Expressions/          表达式：所有 ~40 种表达式节点
│   ├── GeneralScope/         顶层：NamespaceDeclaration/TypeDeclaration/Attribute 等
│   ├── PatternMatching/      模式匹配框架（Match/Choice/Repeat...）
│   └── Tokens.cs             词法 Token 定义（Identifier/Comment/PreProcessorDirective...）
│
├── Transforms/               C# AST 变换管道（14 步）
│   ├── IAstTransform.cs      ★ Transform 接口
│   ├── PatternStatementTransform.cs  模式语句变换
│   ├── DeclareVariables.cs   声明变量
│   ├── FixNameCollisions.cs  解决命名冲突
│   ├── IntroduceUsingDeclarations.cs  引入 using 声明
│   └── ...
│
├── OutputVisitor/            C# AST → 文本输出
│   ├── CSharpOutputVisitor.cs ★ AST 遍历器 → 写入 C# 代码
│   ├── CSharpAmbience.cs     类型/成员简短描述
│   ├── CSharpFormattingOptions.cs  格式化选项
│   ├── ITokenWriter.cs       写入接口
│   ├── TextWriterTokenWriter.cs  写入 TextWriter
│   ├── InsertParenthesesVisitor.cs  自动插入括号
│   ├── InsertRequiredSpacesDecorator.cs  自动插入空格
│   └── InsertMissingTokensDecorator.cs   自动补缺分号/大括号
│
├── Resolver/                 C# 语义解析（类型推断、重载决议、成员查找）
│   ├── CSharpResolver.cs     ★ 核心解析器
│   ├── CSharpConversions.cs  类型转换规则
│   ├── CSharpOperators.cs    运算符解析
│   ├── OverloadResolution.cs 重载决议
│   ├── MemberLookup.cs       成员查找
│   └── TypeInference.cs      类型推断
│
└── ProjectDecompiler/        整项目导出
    ├── WholeProjectDecompiler.cs ★ 遍历所有类型 → 导出 .csproj
    ├── ProjectFileWriterDefault.cs  旧格式 .csproj 写入
    └── ProjectFileWriterSdkStyle.cs SDK 风格 .csproj 写入
```

---

## 四、跨平台共享库 `ICSharpCode.ILSpyX/`

UI 无关的共享逻辑，被 Avalonia UI 和 CLI 共同引用。

| 目录 | 职责 |
|---|---|
| Abstractions/ | ILanguage / IResourceFileHandler 等抽象接口 |
| Analyzers/ | 内置分析器（18 个：MethodUsedBy、TypeExposedBy...） |
| FileLoaders/ | 文件加载器（PE/DLL、存档、Bundle、WebCil...） |
| Search/ | 搜索策略（程序集/成员/元数据 Token/字面量） |
| TreeView/ | 跨平台 TreeView 抽象（SharpTreeNode） |
| Settings/ | ILSpySettings（XML 持久化） |
| Metadata/ | MetadataTableDumper（元数据表导出） |
| PdbProvider/ | PDB 调试信息提供器 |
| MermaidDiagrammer/ | 类图生成器（Mermaid 格式 → HTML） |
| Instrumentation/ | 事件源（ETW） |
| Util/ | GuessFileType 等工具 |

---

## 五、前端 `ILSpy/`（Avalonia UI）

| 目录 | 职责 |
|---|---|
| Program.cs | 入口：单实例检测 + 启动 Avalonia |
| App.axaml / App.axaml.cs | Avalonia 应用配置（主题、MEF 初始化） |
| AppEnv/AppComposition.cs | ★ MEF 组合根（插件扫描、依赖注入） |
| AssemblyTree/ | 左侧：程序集浏览器（树形面板） |
| Languages/ | 语言支持（CSharpLanguage / ILLanguage / ILAst） |
| Analyzers/ | 分析器 UI（AnalyzerTreeView） |
| Metadata/ | 元数据查看器（PE 头、元数据表、流） |
| Search/ | 搜索面板 |
| Bookmarks/ | 书签系统 |
| TextView/ | 右侧：反编译代码视图（AvaloniaEdit） |
| Commands/ | 所有命令（打开/保存/导出/分析...） |
| Options/ | 选项面板（反编译器设置/显示设置） |
| NuGetFeeds/ | NuGet 包源集成 |
| Processes/ | 运行中 .NET 进程附加 |
| Docking/ | Dock 面板布局（wieslawsoltes/Dock） |
| Controls/ | 自定义控件（Omnibar/TreeView/FilterPopup） |

---

## 六、其他子系统

### 6.1 BAML 反编译器 `ICSharpCode.BamlDecompiler/`

WPF/XAML 的 BAML（Binary Application Markup Language）反编译器：

```
Baml/
├── BamlReader.cs          BAML 二进制读取器
├── BamlRecords.cs         BAML 记录类型定义
├── KnownThings.cs         已知成员/类型/关键字表
Handlers/                  记录处理器（Records + Blocks）
Rewrite/                   XAML 重写遍（属性/连接ID/标记扩展）
Xaml/                      XAML 类型模型
XamlDecompiler.cs          ★ XAML 反编译器入口
```

### 6.2 CLI 工具 `ICSharpCode.ILSpyCmd/`

`ilspycmd` 的入口实现：

| 文件 | 职责 |
|---|---|
| IlspyCmdProgram.cs | ★ CLI 主入口（参数解析 + 调度） |
| ILAstDumper.cs | ILAst 文本转储（`--ilast` 标志） |
| TypesParser.cs | 类型过滤器解析 |
| InputFileLoader.cs | 输入文件加载策略 |

### 6.3 VS 扩展 `ILSpy.AddIn/`

Visual Studio 2022 扩展（`net472`）：

- 在 VS 中右键 → Open in ILSpy
- 使用独立的 ILSpy.AddIn.VS2022 项目

### 6.4 测试套件 `ICSharpCode.Decompiler.Tests/`

> 详细的测试编写指南见 [ICSharpCode.Decompiler.Tests/AGENTS.md](../ICSharpCode.Decompiler.Tests/AGENTS.md)

| 目录 | 内容 |
|---|---|
| TestCases/Correctness/ | 正确性测试（50+ .cs/.il/.vb 测试用例） |
| TestCases/ILPretty/ | IL 美化测试 |
| TestCases/Disassembler/ | 反汇编输出测试 |
| Helpers/ | 测试辅助类（CodeAssert/Tester/RoslynToolset） |
| Semantics/ | 语义分析测试 |
| Syntax/ | AST 节点测试 |
| Output/ | 输出格式化测试 |
| ProjectDecompiler/ | 项目导出测试 |
| Metadata/ | 元数据测试 |
| Documentation/ | XML 文档测试 |

---

## 七、关键依赖（NuGet 包）

| 包 | 用途 |
|---|---|
| System.Reflection.Metadata | ECMA-335 元数据读取 |
| Avalonia 12 | 跨平台 GUI 框架 |
| AvaloniaEdit | 代码编辑器控件（语法高亮） |
| Dock (wieslawsoltes/Dock) | 面板布局 |
| Microsoft.Extensions.DependencyInjection | DI 容器 |
| System.Composition | MEF 轻量级实现 |
| Serilog | 日志 |

---

## 实战参考

- [AGENTS.md](../AGENTS.md) — AI Agent 编码指南
- [CONTRIBUTING.md](../CONTRIBUTING.md) — 贡献指南
- 启动路径：`Program.cs → App.axaml.cs → Views/MainWindow.axaml.cs`
- 两个主面板：`AssemblyTree/AssemblyListPane.axaml.cs` + `TextView/DecompilerTextView.axaml.cs`