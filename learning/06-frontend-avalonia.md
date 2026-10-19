# ILSpy 前端架构 — Avalonia UI

> 职责：Avalonia 12 前端层 — MEF 组合根 · 面板系统 · 语言服务 · 命令体系 · 分析器/搜索 · Dock 布局

---

## 数据流视角

```
用户操作 (点击/搜索/拖拽)
    ↓
Avalonia UI 事件
    ↓
Command / ContextMenuEntry
    ↓
语言服务 (CSharpLanguage / ILLanguage)
    ↓
CSharpDecompiler.DecompileAsString()  → C# 文本
    ↓
AvaloniaEdit.Document.Text = code
    ↓
语法高亮 (CSharpHighlightingTokenWriter / AvaloniaEdit highlighting)
```

---

## 一、启动流程

```
Program.Main()
  ├── ShouldStartNewInstance()        ★ 单实例检测（命名管道）
  │     └── 如果已有实例 → 转发参数 → 退出
  │
  ├── BuildAvaloniaApp()
  │     ├── AppBuilder.Configure<App>()
  │     ├── UsePlatformDetect()
  │     └── With(new X11PlatformOptions { OverlayPopups = true })
  │
  └── StartWithClassicDesktopLifetime(args)
        └── App.OnFrameworkInitializationCompleted()
              ├── AppComposition.Initialize()     ★ MEF 容器初始化
              │     ├── RegisterPluginResolver()  扫描 *.Plugin.dll
              │     ├── AssemblyLoadContext.Resolving 钩子
              │     └── CreateContainer()         构建 MEF 组合
              │
              ├── 加载设置 (ILSpySettings)
              ├── 创建 MainWindow
              └── 恢复上次会话 (窗口位置/大小/打开的文件)
```

### 1.1 单实例机制

```csharp
// ILSpy/AppEnv/SingleInstance.cs
static bool TrySignalFirstInstance(CommandLineArguments args)
{
    // 通过命名管道尝试连接已有实例
    // 如果连接成功，转发命令行参数并返回 false（当前进程退出）
    // 如果连接失败，注册为第一个实例并返回 true
}
```

---

## 二、MEF 组合系统

### 2.1 AppComposition — 组合根

```csharp
// ILSpy/AppEnv/AppComposition.cs
public static class AppComposition
{
    static CompositionHost? current;

    public static CompositionHost Current => current
        ?? throw new InvalidOperationException("Composition host not initialized.");

    // 扫描并构建 MEF 容器
    public static CompositionHost Initialize()
    {
        RegisterPluginResolver();  // 一次性：扫描插件 + 注册 AssemblyLoadContext
        return CreateContainer();   // 构建 CompositionHost
    }

    // 安全获取导出（不抛出异常）
    public static T? TryGetExport<T>() where T : class;
    public static IEnumerable<T> TryGetExports<T>() where T : class;

    // 扫描范围：ILSpyX + ILSpy 自身 + *.Plugin.dll
}
```

### 2.2 MEF 导出类型

ILSpy 使用 MEF（`System.Composition`）的 `[Export]` 和 `[Import]` 特性：

```csharp
// 导出命令
[ExportMainMenuCommand(Parent = nameof(Resources.File), Header = "Open...")]
public class OpenCommand : SimpleCommand { ... }

// 导出上下文菜单
[ExportContextMenuEntry(Header = "Analyze")]
public class AnalyzeContextMenuEntry : IContextMenuEntry { ... }

// 导出工具面板
[ExportToolPane(Pane = "Analyzer")]
public class AnalyzerTreeView : IToolPane { ... }

// 导出选项页
[ExportOptionPage(Parent = "Decompiler")]
public class DecompilerSettingsPanel : IOptionPage { ... }

// 注入依赖
[Import] public required LanguageService LanguageService { get; init; }
[ImportMany] public required IEnumerable<ILanguage> Languages { get; init; }
```

### 2.3 插件系统

插件发现机制：

```csharp
// AppComposition - 扫描插件
static IEnumerable<Assembly> LoadPlugins()
{
    var pluginDir = Path.GetDirectoryName(
        typeof(AppComposition).Assembly.Location);
    foreach (var dll in Directory.GetFiles(pluginDir, "*.Plugin.dll"))
    {
        yield return AssemblyLoadContext.Default.LoadFromAssemblyPath(dll);
    }
}
```

---

## 三、主窗口与面板系统

### 3.1 MainWindow 布局

```
┌─────────────────────────────────────────────────────┐
│ Menu (File · Edit · View · Debug · Help)            │
├─────────────────────────────────────────────────────┤
│ Toolbar (Back/Forward · Search · Language Selector)  │
├────────────────────┬────────────────────────────────┤
│                    │                                │
│  Assembly Tree     │  Decompiler TextView            │
│  (左侧面板)         │  (主内容区)                      │
│                    │                                │
│  ├─ Assembly1.dll  │  namespace A {                  │
│  │  ├─ Namespace1  │    class Foo {                  │
│  │  │  ├─ Class1   │      void Bar() {               │
│  │  │  └─ Class2   │        ...                      │
│  │  └─ Namespace2  │      }                          │
│  └─ Assembly2.dll  │    }                            │
│                    │  }                              │
├────────────────────┴────────────────────────────────┤
│ Analyzer / Search / Bookmarks / Metadata (底部面板)   │
├─────────────────────────────────────────────────────┤
│ Status Bar (语言版本 · 光标位置 · 进度)                │
└─────────────────────────────────────────────────────┘
```

### 3.2 核心面板

**AssemblyListPane** — 左侧程序集树：

```csharp
// ILSpy/AssemblyTree/AssemblyListPane.axaml.cs
public partial class AssemblyListPane : UserControl
{
    // AssemblyTreeModel → ObservableCollection<AssemblyTreeNode>
    // 支持拖放 .dll/.exe 文件
    // 右键菜单：打开/移除/分析/导出...
}
```

**DecompilerTextView** — 中央反编译代码视图：

```csharp
// ILSpy/TextView/DecompilerTextView.axaml.cs
public partial class DecompilerTextView : UserControl
{
    // 使用 AvaloniaEdit 的 TextEditor
    // 支持语法高亮、代码折叠、书签
    // 支持 Decompile 方法（异步反编译）
}
```

### 3.3 Dock 布局系统

使用 `wieslawsoltes/Dock` 库实现可停靠面板布局：

```csharp
// ILSpy/Docking/DockWorkspace.cs
// 管理 Dock 工厂 (ILSpyDockFactory)
// 序列化/反序列化布局 (ILSpyDockJson)
// 面板回收 (DockableViewRecycling)
```

---

## 四、语言服务系统

### 4.1 Language 抽象基类

```csharp
// ILSpy/Languages/Language.cs
public abstract class Language : ILanguage
{
    public abstract string Name { get; }              // "C#", "IL", "ILAst"
    public abstract string FileExtension { get; }     // ".cs", ".il"
    public virtual string? ProjectFileExtension => null;  // ".csproj"
    public virtual IBracketSearcher BracketSearcher => DefaultInstance;
    public virtual IReadOnlyList<LanguageVersion> LanguageVersions => [];

    // 导航：成员 → 代码位置映射
    public virtual CodeMappingInfo GetCodeMappingInfo(
        MetadataFile file, EntityHandle member);

    // 反编译：EntityHandle → 文本
    public abstract Task<string> DecompileAsync(
        DecompilationOptions options, EntityHandle handle);
}
```

### 4.2 具体语言实现

| 语言类 | 输出 | 特点 |
|---|---|---|
| `CSharpLanguage` | C# 源码 | 主语言，含语言版本选择器 |
| `ILLanguage` | 原始 IL 指令 | 使用 ReflectionDisassembler |
| `TypedILLanguage` | 类型化 IL | 显示类型信息的 IL |
| `CSharpILMixedLanguage` | C# + IL 混合 | 源码与 IL 并排 |

```csharp
// ILSpy/Languages/CSharpLanguage.cs
public class CSharpLanguage : Language
{
    public override string Name => "C#";
    public override string FileExtension => ".cs";
    public override string ProjectFileExtension => ".csproj";
    public override IBracketSearcher BracketSearcher
        => new CSharpBracketSearcher();

    public override IReadOnlyList<LanguageVersion> LanguageVersions { get; }

    public override async Task<string> DecompileAsync(
        DecompilationOptions options, EntityHandle handle)
    {
        // 创建 CSharpDecompiler → 配置 options → DecompileAsString
    }
}
```

### 4.3 LanguageService

```csharp
// ILSpy/Languages/LanguageService.cs
public class LanguageService
{
    [ImportMany] public IEnumerable<ILanguage> AllLanguages { get; }
    public ILanguage CurrentLanguage { get; set; }

    // 语言间切换时触发重新反编译
    public event EventHandler? CurrentLanguageChanged;
}
```

---

## 五、命令系统

### 5.1 命令注册

```csharp
// 主菜单命令
[ExportMainMenuCommand(Menu = "_File", Header = "_Open...",
    InputGestureText = "Ctrl+O")]
public class OpenCommand : SimpleCommand
{
    public override async void Execute(object? parameter)
    {
        // 文件选择 → 加载程序集
    }
}

// 工具栏命令
[ExportToolbarCommand(ToolTip = "Back",
    ToolbarIcon = "Images.Back", ToolbarCategory = "Navigation")]
public class BrowseBackCommand : SimpleCommand { ... }
```

### 5.2 上下文菜单

```csharp
// ILSpy/ContextMenuEntry.cs
public interface IContextMenuEntry
{
    bool IsVisible(TextViewContext context);
    bool IsEnabled(TextViewContext context);
    void Execute(TextViewContext context);
}

// 导出上下文菜单（自动出现在右键菜单中）
[ExportContextMenuEntry(Header = "Analyze", Icon = "Images.Search")]
public class AnalyzeContextMenuEntry : IContextMenuEntry { ... }
```

---

## 六、分析器与搜索

### 6.1 内置分析器（18 个）

位置：`ICSharpCode.ILSpyX/Analyzers/Builtin/`

| 分析器 | 功能 |
|---|---|
| `MethodUsedByAnalyzer` | 谁调用了此方法 |
| `MethodUsesAnalyzer` | 此方法调用了谁 |
| `MethodOverriddenByAnalyzer` | 被谁重写 |
| `MethodImplementedByAnalyzer` | 被谁实现 |
| `TypeUsedByAnalyzer` | 类型被谁使用 |
| `TypeInstantiatedByAnalyzer` | 类型被谁实例化 |
| `TypeExposedByAnalyzer` | 类型被谁暴露 |
| `TypeExtensionMethodsAnalyzer` | 类型的扩展方法 |
| `FieldAccessAnalyzer` | 字段被谁访问 |
| `EventOverriddenByAnalyzer` | 事件被谁重写 |
| `PropertyOverriddenByAnalyzer` | 属性被谁重写 |
| ... | ... |

```csharp
// 分析器接口
[ExportAnalyzer]
public class MethodUsedByAnalyzer : IAnalyzer
{
    public string Name => "Used By";
    public async Task AnalyzeAsync(IAnalyzerContext context);
}
```

### 6.2 搜索系统

位置：`ICSharpCode.ILSpyX/Search/`

| 搜索策略 | 匹配对象 |
|---|---|
| `AssemblySearchStrategy` | 程序集名 |
| `NamespaceSearchStrategy` | 命名空间 |
| `MemberSearchStrategy` | 成员名（方法/属性/字段） |
| `LiteralSearchStrategy` | 字符串/数字字面量 |
| `MetadataTokenSearchStrategy` | 元数据 Token |
| `ResourceSearchStrategy` | 嵌入资源名 |

---

## 七、设置系统

### 7.1 ILSpySettings — XML 持久化

```csharp
// ICSharpCode.ILSpyX/Settings/ILSpySettings.cs
public class ILSpySettings : ISettingsProvider
{
    // 以 XElement 形式读写各节
    public XElement this[XName section] { get; }

    // 从磁盘加载
    public static ILSpySettings Load();

    // 带互斥锁的保存
    public void SaveSettings(XElement section);
    public void Update(Action<XElement> action);
}
```

### 7.2 设置面板

位置：`ILSpy/Options/`

| 面板 | 内容 |
|---|---|
| `DecompilerSettingsPanel` | 语言版本 / 特性开关 / 格式选项 |
| `DisplaySettingsPanel` | 字体 / 颜色 / 缩进 |
| `MiscSettingsPanel` | 其他杂项设置 |

---

## 实战参考

- [ILSpy/Program.cs](../ILSpy/Program.cs) — 入口
- [ILSpy/AppEnv/AppComposition.cs](../ILSpy/AppEnv/AppComposition.cs) — MEF 组合根
- [ILSpy/AssemblyTree/AssemblyListPane.axaml.cs](../ILSpy/AssemblyTree/AssemblyListPane.axaml.cs) — 程序集树
- [ILSpy/Languages/Language.cs](../ILSpy/Languages/Language.cs) — Language 基类
- [ILSpy/Languages/CSharpLanguage.cs](../ILSpy/Languages/CSharpLanguage.cs) — C# 语言实现
- [ICSharpCode.ILSpyX/Analyzers/](../ICSharpCode.ILSpyX/Analyzers/) — 分析器
- [ILSpy/Commands/](../ILSpy/Commands/) — 命令系统

启动跟踪路径：`Program.cs → App.axaml.cs → Views/MainWindow.axaml.cs → AssemblyListPane + DecompilerTextView`