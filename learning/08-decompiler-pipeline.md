# ILSpy 完整反编译管道

> 职责：反编译全流程 — CSharpDecompiler 主控 · DecompileRun · 错误恢复 · Debug Steps · 整项目导出

---

## 数据流视角

```
┌──────────────────────────────────────────────────────────────────┐
│                      反编译管道架构                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  入口调用:                                                        │
│  CSharpDecompiler.DecompileWholeTypeAsString()                   │
│  CSharpDecompiler.DecompileAsString(methodHandle)                │
│  WholeProjectDecompiler.DecompileProject(module)                 │
│        │                                                         │
│        ▼                                                         │
│  CSharpDecompiler                                                │
│    ├── 加载类型系统 (IDecompilerTypeSystem)                        │
│    ├── 设置 DebugInfoProvider / DocumentationProvider             │
│    │                                                             │
│    ├── [对每个方法] DecompileMethod()                              │
│    │     │                                                       │
│    │     ├─ Step 1: ILReader.ReadIL()                             │
│    │     │     IL 字节码 → ILAst (ILFunction)                     │
│    │     │                                                       │
│    │     ├─ Step 2: IL Transforms (60+ 步)                        │
│    │     │     结构化 ILAst (循环/条件/switch/async/yield...)     │
│    │     │                                                       │
│    │     ├─ Step 3: StatementBuilder.Convert()                    │
│    │     │     ILAst → C# Statement                               │
│    │     │                                                       │
│    │     ├─ Step 4: 构建 C# AST                                    │
│    │     │     MethodDeclaration → BlockStatement → Expressions   │
│    │     │                                                       │
│    │     └─ Step 5: AST Transforms (14 步)                         │
│    │           规范化 C# AST (变量声明/命名冲突/LINQ...)           │
│    │                                                             │
│    └── Step 6: CSharpOutputVisitor.VisitSyntaxTree()              │
│          C# AST → 文本输出                                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 一、CSharpDecompiler — 主调度器

### 1.1 核心 API

```csharp
public class CSharpDecompiler
{
    // === 全类型反编译 ===
    public string DecompileWholeTypeAsString(FullTypeName fullTypeName);
    public string DecompileWholeTypeAsString(ITypeDefinition typeDef);

    // === 单成员反编译 ===
    public string DecompileAsString(EntityHandle handle);
    public string DecompileAsString(MethodDefinitionHandle handle);
    public string DecompileAsString(PropertyDefinitionHandle handle);
    public string DecompileAsString(EventDefinitionHandle handle);

    // === IL 反编译 ===
    public string DecompileILAsString(EntityHandle handle);

    // === 类型分析 ===
    public static bool MemberIsHidden(MetadataFile module, EntityHandle member,
                                       DecompilerSettings settings);

    // === 属性访问 ===
    public IDecompilerTypeSystem TypeSystem { get; }
    public IDebugInfoProvider? DebugInfoProvider { get; set; }
    public IDocumentationProvider? DocumentationProvider { get; set; }
    public Stepper Stepper { get; set; }
    public bool RecordSteps { get; set; }
    public IList<IILTransform> ILTransforms { get; }
    public IList<IAstTransform> AstTransforms { get; }
    public IReadOnlyList<DecompilerException> Errors { get; }
}
```

### 1.2 完整类型反编译流程

```csharp
// DecompileWholeTypeAsString 内部流程
public string DecompileWholeTypeAsString(ITypeDefinition typeDefinition)
{
    // 1. 创建 DecompileRun（单次运行上下文）
    var decompileRun = new DecompileRun();

    // 2. 构建 C# SyntaxTree（含所有成员）
    var syntaxTree = BuildSyntaxTree(typeDefinition);

    // 3. 运行 AST Transforms
    RunTransforms(syntaxTree);

    // 4. 输出为文本
    var sw = new StringWriter();
    var tokenWriter = new TextWriterTokenWriter(sw);
    // 套上装饰器链
    tokenWriter = new InsertRequiredSpacesDecorator(tokenWriter);
    tokenWriter = new InsertMissingTokensDecorator(tokenWriter);
    var visitor = new CSharpOutputVisitor(tokenWriter, formattingOptions);
    syntaxTree.AcceptVisitor(visitor);

    return sw.ToString();
}

// 内部方法构建立流程
SyntaxTree BuildSyntaxTree(ITypeDefinition typeDef)
{
    var syntaxTree = new SyntaxTree();
    var typeDecl = typeSystemAstBuilder.ConvertTypeDefinition(typeDef);
    syntaxTree.Members.Add(typeDecl);

    foreach (var member in typeDef.Members)
    {
        if (MemberIsHidden(module, member.MetadataToken, settings))
            continue;

        try {
            switch (member) {
                case IMethod method:
                    typeDecl.Members.Add(DecompileMethod(method));
                    break;
                case IProperty prop:
                    typeDecl.Members.Add(DecompileProperty(prop));
                    break;
                // ...
            }
        } catch (Exception ex) {
            // 错误恢复：输出注释 + 收集异常
            errors.Add(new DecompilerException(member, ex));
            typeDecl.Members.Add(CreateErrorComment(ex));
        }
    }

    return syntaxTree;
}
```

### 1.3 单方法反编译流程

```csharp
EntityDeclaration DecompileMethod(IMethod method)
{
    // 1. 检查是否有方法体
    if (!method.HasBody) return CreateAbstractMember(method);

    // 2. IL 读取
    var body = module.MetadataFile.GetMethodBody(method.RelativeVirtualAddress);
    var ilReader = new ILReader(module);
    var ilFunction = ilReader.ReadIL(
        methodHandle, body, genericContext,
        ILFunctionKind.TopLevelFunction, cancellationToken);

    // 3. 运行 IL Transforms
    ilFunction.RunTransforms(ilTransforms, new ILTransformContext(...));

    // 4. 转换为 C# AST
    var stmtBuilder = new StatementBuilder(typeSystem, context, ilFunction, ...);
    var csharpBody = stmtBuilder.Convert(ilFunction.Body);

    // 5. 构建 MethodDeclaration
    var decl = new MethodDeclaration {
        Name = method.Name,
        ReturnType = typeSystemAstBuilder.ConvertType(method.ReturnType),
        Body = csharpBody,
        Parameters = BuildParameters(method),
        // ... 修饰符等
    };

    return decl;
}
```

---

## 二、DecompileRun — 运行上下文

```csharp
// ICSharpCode.Decompiler/DecompileRun.cs
public class DecompileRun
{
    public required IDecompilerTypeSystem TypeSystem { get; init; }
    public required DecompilerSettings Settings { get; init; }
    public Disassembler.DisassemblerSignatureTypeProvider? SignatureProvider { get; set; }
    public IDocumentationProvider? DocumentationProvider { get; set; }

    // 用于跟踪已输出的类型/成员（防止重复输出）
    public HashSet<EntityHandle>? DecompiledMembers { get; set; }
}
```

---

## 三、错误恢复机制

ILSpy 在反编译失败时不会中断整个输出，而是优雅降级：

```csharp
// 失败时输出错误注释（保留原 IL 偏移信息）
public static IEnumerable<string> GetErrorCommentLines(Exception error)
{
    yield return error is DecompilerException de
        ? $"ILSpy could not decompile this member: {GetErrorHeadline(de)}"
        : "ILSpy could not decompile this member.";
    yield return "Please report the exception below,";
    yield return "along with the assembly it came from, at " + DecompilationErrorReportUrl;
    foreach (string line in error.ToString().Split('\n'))
        yield return line.TrimEnd('\r');
}

// 错误收集
public IReadOnlyList<DecompilerException> Errors => errors;
```

这意味着：一个类型中某个方法反编译失败不会影响其他方法；CSharpDecompiler.Errors 收集所有失败便于诊断。

---

## 四、Debug Steps — 分步调试

### 4.1 Stepper 机制

```csharp
public class Stepper
{
    public bool SteppingAvailable { get; set; }
    public int? StepLimit { get; set; }         // 限制步数
    public List<StepInfo> Steps { get; }        // 所有步骤记录

    // 步骤编号（仅在 RecordSteps=true 时有意义）
}

// 在 CSharpDecompiler 中启用
decompiler.RecordSteps = true;
decompiler.Stepper.StepLimit = 10;  // 停在 IL Transform 第 10 步
```

当 `RecordSteps = true` 时，IL Transform 和 AST Transform 的每一步都会保存其 ILAst/AST 的快照。这使得 GUI 的 Debug Steps 面板可以按步骤查看反编译的中间状态。

### 4.2 CLI 使用

```bash
# 查看 ILAst（完整 IL 变换管道输出）
ilspycmd MyAssembly.dll -m "MyClass.MyMethod" --ilast

# 在第 N 步后停止
ilspycmd MyAssembly.dll -m "MyClass.MyMethod" --after-transform 5
```

---

## 五、WholeProjectDecompiler — 整项目导出

### 5.1 导出流程

```csharp
// CSharp/ProjectDecompiler/WholeProjectDecompiler.cs
public class WholeProjectDecompiler
{
    public void DecompileProject(
        MetadataFile module,
        string targetDirectory,
        DecompilerSettings settings,
        IProjectInfoProvider projectInfoProvider)
    {
        // 1. 创建项目文件写入器
        IProjectFileWriter writer = projectInfoProvider.IsSdkStyle
            ? new ProjectFileWriterSdkStyle()
            : new ProjectFileWriterDefault();

        // 2. 遍历所有类型
        foreach (var typeDef in typeSystem.MainModule.TypeDefinitions)
        {
            // 3. 每个类型反编译为独立 .cs 文件
            string code = decompiler.DecompileWholeTypeAsString(typeDef);

            // 4. 确定文件路径
            string filePath = DetermineFilePath(typeDef, targetDirectory);
            Directory.CreateDirectory(Path.GetDirectoryName(filePath));
            File.WriteAllText(filePath, code);
        }

        // 5. 写入项目文件
        writer.WriteProjectFile(targetDirectory, ...);

        // 6. 输出汇编信息（AssemblyInfo）
        WriteAssemblyInfo(module, targetDirectory);
    }
}
```

### 5.2 CLI 导出

```bash
ilspycmd MyAssembly.dll -o ./output --project
```

---

## 六、TypeSystemAstBuilder — 类型系统到 AST

将类型系统实体转换为 C# 语法树节点的关键组件：

```csharp
// CSharp/Syntax/TypeSystemAstBuilder.cs
public class TypeSystemAstBuilder
{
    // 类型 → AST 类型引用
    public AstType ConvertType(IType type);

    // 类型定义 → TypeDeclaration
    public TypeDeclaration ConvertTypeDefinition(ITypeDefinition typeDef);

    // 方法 → MethodDeclaration
    public MethodDeclaration ConvertMethod(IMethod method);

    // 属性 → PropertyDeclaration
    public PropertyDeclaration ConvertProperty(IProperty property);

    // 字段 → FieldDeclaration
    public FieldDeclaration ConvertField(IField field);

    // 使用当前上下文推断 using / 类型简写
    public bool UseNullableSpecifier { get; set; }
    public bool ShowAttributes { get; set; }
}
```

---

## 实战参考

- [CSharp/CSharpDecompiler.cs](../ICSharpCode.Decompiler/CSharp/CSharpDecompiler.cs) — 主调度器
- [CSharp/DecompileRun.cs](../ICSharpCode.Decompiler/DecompileRun.cs) — 运行上下文
- [CSharp/ProjectDecompiler/WholeProjectDecompiler.cs](../ICSharpCode.Decompiler/CSharp/ProjectDecompiler/WholeProjectDecompiler.cs) — 整项目导出
- [CSharp/Syntax/TypeSystemAstBuilder.cs](../ICSharpCode.Decompiler/CSharp/Syntax/TypeSystemAstBuilder.cs) — TypeSystem → AST
- [DebugSteps/Stepper.cs](../ICSharpCode.Decompiler/DebugSteps/Stepper.cs) — 分步调试
- [ICSharpCode.Decompiler.Tests/AGENTS.md](../ICSharpCode.Decompiler.Tests/AGENTS.md) — 测试编写指南