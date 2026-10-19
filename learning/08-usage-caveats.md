# ILSpy 使用陷阱与注意事项

> 职责：全程伴随的陷阱清单 — 开发环境 · API 使用 · 测试 · 构建脚本 · 平台差异

---

## 一、构建与环境陷阱

### 1.1 恢复依赖必须用脚本

**陷阱**：直接用 `dotnet restore` 会裁剪 `packages.lock.json`。

```powershell
# 错误
dotnet restore ILSpy.sln

# 正确
.\restore.ps1
```

**原因**：`restore.ps1` 传入 `-p:RestoreEnablePackagePruning=false`，防止 NuGet 裁剪锁文件中的传递依赖项。如果误用了 `dotnet restore`，用 `git checkout -- **/packages.lock.json` 恢复。

### 1.2 构建也必须用脚本

```powershell
# 正确
.\restore.ps1
.\build.ps1 -Configuration Debug
```

`build.ps1` 默认传入 `--no-restore`，先单独 restore 再 build 可以防止隐式 restore 触发的锁文件裁剪。

### 1.3 编译目标框架选择

部分项目面向 `net472`（VS 扩展、安装器），它们无法在 Linux/macOS 上编译：

```powershell
# 在非 Windows 上构建跨平台子集
dotnet build ILSpy.XPlat.slnf

# 或在 Windows 上跳过 VS 扩展
dotnet build ILSpy.Desktop.slnf
```

### 1.4 .NET SDK 版本

- 主应用目标 `net10.0`
- 测试项目目标 `net11.0`（及 `net11.0-windows` 用于 Windows 专用测试）
- **不要随意修改 TFM（Target Framework Moniker）**

---

## 二、API 使用陷阱

### 2.1 CSharpDecompiler 不线程安全

**陷阱**：多个线程共用一个 `CSharpDecompiler` 实例。

```csharp
// 错误
var decompiler = new CSharpDecompiler("a.dll", settings);
Parallel.ForEach(methods, m => {
    var code = decompiler.DecompileAsString(m);  // 竞态条件！
});

// 正确：每个线程自己创建实例
Parallel.ForEach(methods, m => {
    var decompiler = new CSharpDecompiler("a.dll", settings);
    var code = decompiler.DecompileAsString(m);
});
```

**原因**：`CSharpDecompiler` 内部持有 Transform 实例状态，不是线程安全的。

### 2.2 PEFile 必须 Dispose

```csharp
// 错误
var file = new PEFile("a.dll", stream, PEStreamOptions.PrefetchEntireImage);
// ... 使用 ...
// 忘记 Dispose() → 文件锁定

// 正确
using var file = new PEFile("a.dll", stream, PEStreamOptions.PrefetchEntireImage);
```

### 2.3 DecompilerSettings 影响巨大

**陷阱**：不同 `LanguageVersion` 设置会产生完全不同的反编译输出。

```csharp
// CSharp1 输出：int i; i = 5;
var s1 = new DecompilerSettings(LanguageVersion.CSharp1);

// Latest 输出：int i = 5; (init 访问器 / nint / record 等现代语法)
var s2 = new DecompilerSettings(LanguageVersion.Latest);

// 比较反编译输出前，确保 settings 一致
```

### 2.4 DecompilerSettings.SetLanguageVersion 只降不升

```csharp
var settings = new DecompilerSettings();

// 关闭 C# 10+ 特性
settings.SetLanguageVersion(LanguageVersion.CSharp7);

// 不能再恢复 - 特性标志已经被关闭了！
// 需要重新创建 settings
settings = new DecompilerSettings(LanguageVersion.Latest);
```

`SetLanguageVersion` 将语言特性标志设为指定版本的状态，后续调用更高版本不会重新启用。

---

## 三、测试陷阱

### 3.1 ILSpy-tests 子模块

**陷阱**：clone 后直接运行测试，许多测试被跳过。

```powershell
# 必须初始化子模块
git submodule update --init ILSpy-tests
```

**原因**：`ILSpy-tests/` 包含大型真实世界的测试程序集（如 `FSharp.Core.dll`），默认不检出。测试在子模块缺失时会 `Assert.Ignore` 而非失败。

### 3.2 测试运行需要 TRX 报告

```powershell
# 正确（保存失败详情）
dotnet test --solution ILSpy.sln --report-trx

# 避免：不加 --report-trx 时失败信息会在滚动后丢失
```

### 3.3 格式化提交

**陷阱**：使用 `--no-verify` 跳过 pre-commit 钩子。

```powershell
# 错误（跳过格式化）
git commit -m "fix" --no-verify

# 正确（让钩子运行 dotnet format）
git commit -m "fix bug in decompiler"
```

Pre-commit 钩子对整个 solution 运行 `dotnet format`。绕过它会导致未格式化的代码进入仓库。

### 3.4 文件换行符

**陷阱**：在 Linux/macOS 上运行 `unix2dos` 或其他换行符转换工具。

- **Windows**：新文件保存为 CRLF
- **Linux/macOS**：新文件保存为 LF
- 不要手动转换，Git 的 `* text=auto` 会自动处理

---

## 四、编码规范陷阱

### 4.1 文件头

每个新 `.cs` 文件需要 MIT X11 许可证头：

```csharp
// Copyright (c) <year> <human name>
//
// Permission is hereby granted, free of charge, ...
```

- 不要添加 AI 代理作为版权人
- 不要修改已有文件的版权头
- 旧的无头文件保持原样

### 4.2 注释规范

**陷阱**：写"本次修改..."、"新的实现..."等描述变更历史的注释。

```csharp
// 错误
// We changed this to use IEnumerable<T> instead of T[]
// Now the null check is at the beginning

// 正确
// Filters items by the given predicate and returns the result.
```

注释必须独立可读，不能依赖"当时的对话/PR"上下文。

### 4.3 ASCII 专用

所有代码和注释使用 ASCII 字符。不要使用 em-dash（—）、智能引号、Unicode 箭头、数学符号等。

---

## 五、反编译器特定陷阱

### 5.1 ILAst 的 SlotInfo 生命周期

IAst 指令的 `SlotInfo` 关联了变量定义，在 Transform 中如果拆分/内联变量，必须同时更新 SlotInfo，否则后续的 `StatementBuilder` 会获取到错误的变量引用。

### 5.2 Block 的 Post-order 遍历

在编写 IL Transform 时，注意 `BlockILTransform` 是后序遍历的（先处理子 Block 再处理当前 Block）。如果你的 Transform 依赖于父 Block 的特定状态，不要放入 `BlockILTransform` 中。

### 5.3 StatementTransform 的重新运行机制

`StatementTransform` 内部的子 Transform 会触发重新运行（当 `RequestRerun()` 被调用时）：

```csharp
// 在 StatementTransform 中：
// ILInlining 内联了一个变量后
// → ExpressionTransforms 可能发现新的可折叠表达式
// → TransformAssignment 可能发现新的赋值模式
// → 重新运行整个链
```

如果添加新的子 Transform 到 `StatementTransform`，确保调用 `RequestRerun()` 当你的变换开辟了新的优化机会。

### 5.4 MemberIsHidden 判断

`MemberIsHidden` 决定了某些编译器生成的成员是否显示在反编译输出中。如果新增了编译器模式识别（如新的 async 模式），需要在 `MemberIsHidden` 中添加对应的检查，否则会产生重复输出。

---

## 六、平台特定陷阱

### 6.1 Linux

```bash
# X11: OverlayPopups 必须为 true
# 否则弹出菜单（如下拉框）会在显示后 100ms 内自行关闭
# 这已在 Program.cs 中配置: new X11PlatformOptions { OverlayPopups = true }
```

### 6.2 macOS

- 应用程序包签名需要在 `BuildTools/packaging/macos/` 中处理
- `Assets/macos/Info.plist` 定义了应用元数据

### 6.3 跨平台通用

- 文件路径分隔符：始终使用 `Path.Combine` / `Path.DirectorySeparatorChar`
- 进程附加（`ILSpy/Processes/`）：Windows 和 Linux 有不同的实现策略

---

## 七、依赖管理陷阱

### 7.1 Central Package Management

项目使用集中包管理（`Directory.Packages.props`）：

```xml
<!-- 错误：直接在 csproj 中写 Version -->
<PackageReference Include="Newtonsoft.Json" Version="13.0.0" />

<!-- 正确：Version 在 Directory.Packages.props 中定义 -->
<PackageReference Include="Newtonsoft.Json" />
```

### 7.2 更新依赖

```powershell
# 更新包 → 重新生成锁文件
.\updatedeps.ps1

# 然后提交锁文件变更
git add **/packages.lock.json
```

---

## 八、调试技巧

### 8.1 Debug Steps

```csharp
// 在 GUI 中启用 Debug Steps
decompiler.RecordSteps = true;
decompiler.Stepper.StepLimit = 10;

// CLI
ilspycmd MyAssembly.dll -m "MyMethod" --after-transform 5
```

### 8.2 验证 ILAst

```bash
# 查看 IL Transform 管道的完整输出
ilspycmd MyAssembly.dll -m "MyMethod" --ilast

# 与最终 C# 输出对比
ilspycmd MyAssembly.dll -m "MyMethod"
```

### 8.3 查看原始 IL

```csharp
// 编程 API
string il = decompiler.DecompileILAsString(methodHandle);

// CLI
ilspycmd MyAssembly.dll --il
```

---

## 九、常见问题速查

| 症状 | 可能原因 | 解决 |
|---|---|---|
| 文件被锁定无法替换 | `PEFile` 未 Dispose | `using var file = new PEFile(...)` |
| `packages.lock.json` 被意外修改 | 用了 `dotnet restore` | `git checkout -- **/packages.lock.json` |
| 测试全部通过但 round-trip 测试没运行 | `ILSpy-tests/` 为空 | `git submodule update --init` |
| 编译失败: `XA5300` | Android TFM 问题 | 换用 `ILSpy.Desktop.slnf` |
| Pre-commit 钩子很慢 | `dotnet format` 对整个 solution 运行 | 这是正常现象，请耐心等待 |
| 反编译输出与上次不同 | 语言版本设置不同 | 检查 `DecompilerSettings.LanguageVersion` |

---

## 实战参考

- [AGENTS.md](../AGENTS.md) — AI Agent 编码指南
- [CONTRIBUTING.md](../CONTRIBUTING.md) — 贡献指南
- [Directory.Packages.props](../Directory.Packages.props) — 集中包管理
- [BuildTools/format.ps1](../BuildTools/format.ps1) — 格式化脚本
- [restore.ps1](../restore.ps1) — 恢复脚本