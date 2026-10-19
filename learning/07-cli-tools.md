# ILSpy CLI 工具与 PowerShell

> 职责：命令行工具 — ilspycmd · PowerShell Cmdlet · Docker 容器 · BAML 处理

---

## 数据流视角

```
命令行参数 (argv[])
    ↓
IlspyCmdProgram.Main()
    ├── 参数解析 (System.CommandLine)
    ├── 文件加载 (InputFileLoader)
    │     ├── PEFileLoader    → PEFile
    │     ├── BundleFileLoader → PEFile (从 bundle 中提取)
    │     └── ArchiveFileLoader→ PEFile (从 .zip 中提取)
    ├── 类型过滤 (TypesParser)
    └── 反编译调度
          ├── 单个文件: CSharpDecompiler.DecompileWholeTypeAsString()
          ├── 整项目: WholeProjectDecompiler.DecompileProject()
          └── ILAst: ILAstDumper.Dump()
```

---

## 一、ilspycmd — 命令行反编译器

### 1.1 安装与基本用法

```bash
# 全局安装
dotnet tool install --global ilspycmd

# 基本用法
ilspycmd MyAssembly.dll                           # 反编译并输出到控制台
ilspycmd MyAssembly.dll -o ./output               # 输出到目录
ilspycmd MyAssembly.dll --project                 # 输出为 .csproj 项目
ilspycmd MyAssembly.dll -m "MyClass.MyMethod"     # 反编译指定成员
ilspycmd MyAssembly.dll -t "MyNamespace.*"        # 过滤类型
ilspycmd MyAssembly.dll --il                      # 显示 IL（而非 C#）
ilspycmd MyAssembly.dll --ilast                   # 显示 ILAst
ilspycmd MyAssembly.dll --after-transform 5       # 在第 5 步后停止
```

### 1.2 完整参数列表

| 参数 | 说明 |
|---|---|
| `<assembly>` | 要反编译的程序集路径（位置参数） |
| `-o, --outputdir` | 输出目录 |
| `-p, --project` | 生成为 .csproj 项目 |
| `-m, --member` | 反编译特定成员（使用 DocId 格式） |
| `-t, --type` | 类型过滤器（支持通配符） |
| `-l, --list` | 列出程序集中的类型 |
| `-il, --il-code` | 显示 IL 代码 |
| `--ilast` | 显示 ILAst（IL 中间表示） |
| `--after-transform` | 在指定变换步骤后停止 |
| `--language-version` | C# 语言版本（如 CSharp8） |
| `-r, --reference` | 额外的引用程序集路径 |
| `--no-dead-stores` | 移除死变量存储 |
| `--no-dead-code` | 移除死代码 |
| `--no-color` | 禁用彩色输出 |

### 1.3 入口实现

```csharp
// ICSharpCode.ILSpyCmd/IlspyCmdProgram.cs
public class IlspyCmdProgram
{
    public static async Task<int> Main(string[] args)
    {
        // 1. 解析命令行参数
        var options = ParseCommandLine(args);

        // 2. 加载程序集
        var file = await InputFileLoader.LoadAsync(options.AssemblyPath);

        // 3. 配置反编译器
        var settings = new DecompilerSettings(options.LanguageVersion);
        var typeSystem = new DecompilerTypeSystem(file, resolver, settings);
        var decompiler = new CSharpDecompiler(typeSystem, settings);

        // 4. 根据模式反编译
        if (options.ListTypes)
        {
            foreach (var td in typeSystem.MainModule.TypeDefinitions)
                Console.WriteLine(td.FullName);
        }
        else if (options.Member != null)
        {
            // 反编译单个成员
            var handle = FindMember(typeSystem, options.Member);
            var code = decompiler.DecompileAsString(handle);
            Console.WriteLine(code);
        }
        else if (options.OutputDirectory != null)
        {
            // 导出项目
            new WholeProjectDecompiler().DecompileProject(
                file, options.OutputDirectory, settings, ...);
        }

        // 5. 检查错误
        if (decompiler.Errors.Count > 0)
        {
            foreach (var error in decompiler.Errors)
                Console.Error.WriteLine(CSharpDecompiler.GetErrorHeadline(error));
            return ProgramExitCodes.DecompilationErrors;
        }

        return ProgramExitCodes.Success;
    }
}
```

---

## 二、输入文件加载策略

```csharp
// ICSharpCode.ILSpyCmd/InputFileLoader.cs
public static class InputFileLoader
{
    public static async Task<PEFile> LoadAsync(string path)
    {
        // 尝试顺序：
        // 1. 标准 PE 文件 (.dll/.exe)
        // 2. .NET 单文件 Bundle (extract)
        // 3. ZIP 存档中的文件 (archive::path.zip#internal.dll)
        // 4. NuGet 包中的文件

        using var registry = new FileLoaderRegistry();
        var result = await registry.Load(path);
        return result?.MetadataFile as PEFile
            ?? throw new FileNotFoundException($"Cannot load: {path}");
    }
}
```

---

## 三、ILAst 转储

```csharp
// ICSharpCode.ILSpyCmd/ILAstDumper.cs
public static class ILAstDumper
{
    // 将 ILAst 以文本形式输出（带缩进、颜色）
    public static string Dump(ILFunction function, ILAstWritingOptions options)
    {
        // 递归遍历 IL 指令树
        // 格式化输出（类似 IL 语法，但带结构化信息）
        // 支持 --after-transform 在指定步骤停止
    }
}
```

示例输出：

```
IL_0000: nop
IL_0001: ldarg.0
IL_0002: call get_Now()
IL_0007: stloc V_0
IL_0008: br IL_000e
IL_000d: nop
IL_000e: ldloc V_0
IL_000f: call Console.WriteLine(DateTime)
IL_0014: ret
```

---

## 四、PowerShell Cmdlet

### 4.1 安装

```powershell
# 从 PowerShell Gallery 安装
Install-Module -Name ICSharpCode.Decompiler.PowerShell

# 导入模块
Import-Module ICSharpCode.Decompiler.PowerShell
```

### 4.2 Cmdlet 一览

| Cmdlet | 功能 |
|---|---|
| `Get-Decompiler` | 创建 Decompiler 对象 |
| `Get-DecompiledSource` | 反编译为源码字符串 |
| `Get-DecompiledTypes` | 列出反编译后的类型 |
| `Get-DecompiledProject` | 导出为项目 |
| `Get-DecompilerVersion` | 获取版本信息 |
| `Get-TargetFramework` | 获取目标框架 |

### 4.3 使用示例

```powershell
# 创建反编译器
$decompiler = Get-Decompiler -Path "MyAssembly.dll" -LanguageVersion Latest

# 反编译单个类型
Get-DecompiledSource -Decompiler $decompiler -TypeName "MyNamespace.MyClass"

# 列出所有类型
Get-DecompiledTypes -Decompiler $decompiler -Filter "MyNamespace.*"

# 反编译并导出项目
Get-DecompiledProject -Decompiler $decompiler -OutputPath "./output"

# 管道操作
Get-Decompiler "MyAssembly.dll" |
    Get-DecompiledTypes -Filter "*.Service" |
    ForEach-Object { $_.FullName }
```

---

## 五、BAML/XAML 反编译

### 5.1 CLI 集成

```bash
# 反编译 WPF 程序集的 BAML 资源
ilspycmd MyWpfApp.exe --baml

# 输出为 XAML 文件
```

### 5.2 BamlAwareWholeProjectDecompiler

```csharp
// ICSharpCode.ILSpyCmd/BamlAwareWholeProjectDecompiler.cs
public class BamlAwareWholeProjectDecompiler
{
    // 增强的项目导出：同时反编译 BAML 资源为 XAML 文件
    // 处理 .baml → .xaml 转换
    // 生成 .csproj 中的 XAML 页面引用
}
```

---

## 六、Docker 支持

```dockerfile
# ICSharpCode.ILSpyCmd/AsContainer/Dockerfile
FROM mcr.microsoft.com/dotnet/runtime:10.0
COPY ./published /app
ENTRYPOINT ["dotnet", "/app/ilspycmd.dll"]
```

```bash
# 构建 Docker 镜像
docker build -t ilspycmd -f AsContainer/Dockerfile .

# 使用容器运行
docker run --rm -v $(pwd):/data ilspycmd /data/MyAssembly.dll -o /data/output
```

---

## 七、程序退出码

```csharp
// ICSharpCode.ILSpyCmd/ProgramExitCodes.cs
public static class ProgramExitCodes
{
    public const int Success = 0;
    public const int DecompilationErrors = 1;   // 反编译过程中有错误
    public const int InvalidArguments = 2;       // 参数无效
    public const int AssemblyNotFound = 3;       // 程序集未找到
}
```

---

## 实战参考

- [ICSharpCode.ILSpyCmd/](../ICSharpCode.ILSpyCmd/) — CLI 实现
- [ICSharpCode.ILSpyCmd/IlspyCmdProgram.cs](../ICSharpCode.ILSpyCmd/IlspyCmdProgram.cs) — 入口
- [ICSharpCode.ILSpyCmd/ILAstDumper.cs](../ICSharpCode.ILSpyCmd/ILAstDumper.cs) — IL 转储
- [ICSharpCode.ILSpyCmd/InputFileLoader.cs](../ICSharpCode.ILSpyCmd/InputFileLoader.cs) — 文件加载
- [ICSharpCode.Decompiler.PowerShell/](../ICSharpCode.Decompiler.PowerShell/) — PowerShell 模块
- [ICSharpCode.Decompiler.PowerShell/Demo.ps1](../ICSharpCode.Decompiler.PowerShell/Demo.ps1) — 示例脚本
- [ICSharpCode.Decompiler/CSharp/ProjectDecompiler/WholeProjectDecompiler.cs](../ICSharpCode.Decompiler/CSharp/ProjectDecompiler/WholeProjectDecompiler.cs) — 项目导出引擎