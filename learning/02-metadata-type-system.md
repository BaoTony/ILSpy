# ILSpy 元数据加载与类型系统

> 职责：元数据层 + 类型系统抽象 — PEFile/MetadataFile 加载 · IType/IMethod 接口体系
约占反编译器核心库 1/5

---

## 数据流视角

```
.dll/.exe 文件
  → FileStream
  → PEFile (PEReader + MetadataReader 封装)
    → MetadataFile (抽象基类，含 AssemblyResolver)
      → DecompilerTypeSystem
        → ICompilation → IDecompilerTypeSystem
          ├── MainModule: MetadataModule
          ├── IType (类型)
          ├── IMethod (方法)
          ├── IField (字段)
          ├── IProperty (属性)
          ├── IEvent (事件)
          └── ...

  → CSharpDecompiler(typeSystem, settings)
    → DecompileWholeTypeAsString()  ← 管道起点
```

---

## 一、文件加载体系

### 1.1 文件加载器注册表

ILSpy 支持多种文件格式，通过 `FileLoaderRegistry` 统一管理：

```
FileLoaderRegistry
├── PEFileLoader        ★ 标准 .NET PE 文件 (DLL/EXE)
├── BundleFileLoader     .NET 单文件 bundle
├── ArchiveFileLoader    ZIP 存档中的文件
├── WebCilFileLoader    WebCil 格式
├── XamarinCompressedFileLoader  Xamarin 压缩程序集
└── MetadataFileLoader  纯元数据文件
```

每个加载器实现 `IFileLoader`，尝试识别文件格式并返回 `LoadResult`：

```csharp
// ICSharpCode.ILSpyX/FileLoaders/IFileLoader
public interface IFileLoader
{
    Task<LoadResult?> Load(string fileName, Stream stream, FileLoadContext context);
}

public struct LoadResult
{
    public MetadataFile? MetadataFile { get; set; }
    // ...
}
```

### 1.2 PEFileLoader — 主流程

```csharp
// ICSharpCode.ILSpyX/FileLoaders/PEFileLoader.cs
public async Task<LoadResult?> Load(string fileName, Stream stream, FileLoadContext context)
{
    // 1. 检查 MZ 文件头
    if (stream.ReadByte() != 'M' || stream.ReadByte() != 'Z') return null;

    // 2. 创建 PEFile 实例
    PEFile module = new PEFile(fileName, stream,
        PEStreamOptions.PrefetchEntireImage | PEStreamOptions.LeaveOpen,
        metadataOptions: options);

    return new LoadResult { MetadataFile = module };
}
```

### 1.3 PEFile 类

```csharp
// ICSharpCode.Decompiler/Metadata/PEFile.cs
public sealed class PEFile : MetadataFile, IDisposable
{
    public PEReader Reader { get; }            // PE 读取器
    public MetadataReader Metadata { get; }    // ECMA-335 元数据读取器
    public string FileName { get; }
    public TargetRuntime TargetRuntime { get; }
    // ... 元数据表查询方法
}
```

`PEFile` 封装了 `System.Reflection.Metadata` 库的 `PEReader` 和 `MetadataReader`，提供了更高级的查询接口。

### 1.4 程序集解析

```
UniversalAssemblyResolver (ICSharpCode.Decompiler.Metadata)
├── 搜索路径:
│   ├── 主程序集所在目录
│   ├── .NET Core/Framework 运行时目录
│   ├── NuGet 包缓存 (%userprofile%\.nuget)
│   └── 自定义搜索路径
└── Resolve(IAssemblyReference) → MetadataFile
```

---

## 二、类型系统接口体系

ILSpy 不直接使用 `System.Reflection`，而是构建了自己的类型系统抽象层。这是整个反编译器的基础。

### 2.1 接口继承层次

```
ISymbol (名称)
├── IEntity (元数据 Token + 属性)
│   ├── ITypeDefinition (类型定义)
│   └── IMember (成员)
│       ├── IMethod (方法)
│       ├── IField (字段)
│       ├── IProperty (属性)
│       └── IEvent (事件)
│
├── IType (类型引用)
│   ├── ITypeDefinition
│   └── ITypeParameter (泛型参数)
│
├── IParameter (方法参数)
├── IVariable (局部变量)
└── INamespace (命名空间)

ICompilation (编译单元)
└── IDecompilerTypeSystem (反编译器类型系统根)
```

### 2.2 核心接口定义

```csharp
// ICSharpCode.Decompiler/TypeSystem/ISymbol.cs
public interface ISymbol
{
    SymbolKind SymbolKind { get; }
    string? Name { get; }
}

// ICSharpCode.Decompiler/TypeSystem/IEntity.cs
public interface IEntity : ISymbol, ICompilationProvider
{
    EntityHandle MetadataToken { get; }
    Accessibility Accessibility { get; }
    bool IsStatic { get; }
    bool IsAbstract { get; }
    bool IsSealed { get; }
    bool IsVirtual { get; }
    bool IsOverride { get; }
    ITypeDefinition? DeclaringTypeDefinition { get; }
    IReadOnlyList<IAttribute> GetAttributes();
}

// ICSharpCode.Decompiler/TypeSystem/IMethod.cs
public interface IMethod : IMember, IParameterizedMember
{
    IReadOnlyList<ITypeParameter> TypeParameters { get; }
    IReadOnlyList<IParameter> Parameters { get; }
    IType ReturnType { get; }
    bool IsConstructor { get; }
    bool IsDestructor { get; }
    bool IsOperator { get; }
    bool IsAccessor { get; }
    bool HasBody { get; }
}

// ICSharpCode.Decompiler/TypeSystem/IField.cs
public interface IField : IMember
{
    IType Type { get; }
    bool IsReadOnly { get; }
    bool IsVolatile { get; }
    bool IsConst { get; }
    object? GetConstantValue();
}

// ICSharpCode.Decompiler/TypeSystem/IProperty.cs
public interface IProperty : IMember, IParameterizedMember
{
    IType ReturnType { get; }
    bool CanGet { get; }
    bool CanSet { get; }
    IMethod? Getter { get; }
    IMethod? Setter { get; }
}

// ICSharpCode.Decompiler/TypeSystem/IType.cs
public interface IType : ITypeResolveContext, ISymbol
{
    TypeKind Kind { get; }              // Class/Struct/Interface/Enum/...
    bool? IsReferenceType { get; }
    IType? DeclaringType { get; }
    int TypeParameterCount { get; }
    IReadOnlyList<IType> TypeArguments { get; }

    // 类型操作方法
    IType AcceptVisitor(TypeVisitor visitor);
    IType VisitChildren(TypeVisitor visitor);

    // 获取成员
    IEnumerable<IMethod> GetMethods(...);
    IEnumerable<IField> GetFields(...);
    IEnumerable<IProperty> GetProperties(...);
    IEnumerable<IEvent> GetEvents(...);
}
```

### 2.3 类型系统实现类

上部是对外接口，下部是具体实现（`TypeSystem/Implementation/`）：

```
接口层 (TypeSystem/)
    接口: ISymbol / IEntity / IType / IMethod / IField / IProperty / ...

实现层 (TypeSystem/Implementation/)
    具体类:
    ├── MetadataModule            ★ 模块：持有 PEFile + 解析器
    ├── MetadataTypeDefinition    ★ 类型定义（类/结构体/接口/枚举/委托）
    ├── MetadataMethod            方法定义
    ├── MetadataField             字段定义
    ├── MetadataProperty          属性定义
    ├── MetadataEvent             事件定义
    ├── MetadataParameter         参数定义
    ├── MetadataTypeParameter     泛型参数
    ├── MetadataNamespace         命名空间

    泛型特化 (Specialized*):
    ├── SpecializedMethod         IMethod 的特化实例（填充类型实参）
    ├── SpecializedField
    ├── SpecializedProperty
    └── SpecializedEvent

    复合类型:
    ├── ArrayType                 数组类型 T[]
    ├── ByReferenceType           ref T
    ├── PointerType               T*
    ├── ParameterizedType         List<int> (泛型实例化)
    ├── NullableType              int?
    ├── TupleType                 (int, string)
    ├── FunctionPointerType       delegate*<...>
    └── ModifiedType              修饰类型 (volatile/const/...)
```

### 2.4 DecompilerTypeSystem — 根对象

```csharp
// ICSharpCode.Decompiler/TypeSystem/DecompilerTypeSystem.cs
public class DecompilerTypeSystem : IDecompilerTypeSystem
{
    public MetadataModule MainModule { get; }           // 主模块
    public IReadOnlyList<MetadataModule> Modules { get; } // 所有模块
    public IAssemblyResolver AssemblyResolver { get; }
    public IInterningProvider? InterningProvider { get; }

    // 创建方式
    public DecompilerTypeSystem(
        MetadataFile mainModule,
        IAssemblyResolver assemblyResolver,
        DecompilerSettings settings)
    { ... }
}
```

---

## 三、类型系统关键操作

### 3.1 从 Handle 到 IType

```csharp
// TypeDefinitionHandle → ITypeDefinition
var typeSystem = decompiler.TypeSystem;
var module = typeSystem.MainModule;
ITypeDefinition typeDef = module.GetTypeDefinition(typeDefHandle);

// MethodDefinitionHandle → IMethod
IMethod method = module.GetMethod(methodHandle);

// FieldDefinitionHandle → IField
IField field = module.GetField(fieldHandle);
```

### 3.2 GetMembers 与过滤

```csharp
// 获取公共方法
var publicMethods = typeDef.GetMethods(
    options: GetMemberOptions.IgnoreInheritedMembers)
    .Where(m => m.Accessibility == Accessibility.Public);

// 获取所有成员
var allMembers = typeDef.GetMembers();

// 获取属性（含继承）
var properties = typeDef.GetProperties(
    options: GetMemberOptions.IgnoreInheritedMembers);
```

### 3.3 FullTypeName — 类型标识

```csharp
public struct FullTypeName
{
    public TopLevelTypeName TopLevelTypeName;   // 顶级类型名
    public string? NestedTypeName;              // 嵌套类型名（可选）
    public int TypeParameterCount;              // 泛型参数数量

    // 常用构造
    public FullTypeName(string topLevelTypeName);
    public FullTypeName(string namespaceName, string name, int typeParameterCount);
}

// 使用
var ftn = new FullTypeName("System.Collections.Generic.List");
var typeDef = decompiler.TypeSystem.MainModule.GetTypeDefinition(ftn);
```

---

## 四、MetadataModule — 模块容器

```csharp
// ICSharpCode.Decompiler/TypeSystem/MetadataModule.cs
public class MetadataModule
{
    public PEFile MetadataFile { get; }              // 底层 PE 文件
    public IAssemblyResolver AssemblyResolver { get; }
    public TypeSystemOptions TypeSystemOptions { get; }
    public ICompilation Compilation { get; }

    // 命名空间与类型
    public IEnumerable<ITypeDefinition> TypeDefinitions { get; }
    public IEnumerable<INamespace> RootNamespaces { get; }

    // Handle → IType/IMethod/... 解析方法
    public ITypeDefinition GetTypeDefinition(TypeDefinitionHandle handle);
    public IMethod GetMethod(MethodDefinitionHandle handle);
    public IField GetField(FieldDefinitionHandle handle);
    public IProperty GetProperty(PropertyDefinitionHandle handle);
    public IEvent GetEvent(EventDefinitionHandle handle);

    // FullTypeName → ITypeDefinition
    public ITypeDefinition? GetTypeDefinition(FullTypeName fullTypeName);
    public ITypeDefinition? GetTypeDefinition(TopLevelTypeName topLevelTypeName);

    // 解析类型引用 (TypeReferenceHandle → IType)
    public IType? ResolveType(TypeReferenceHandle handle, ...);
}
```

---

## 五、GenericContext — 泛型上下文

```csharp
// 泛型上下文的类型参数映射
public struct GenericContext
{
    public IEnumerable<ITypeParameter>? ClassTypeParameters;
    public IEnumerable<ITypeParameter>? MethodTypeParameters;

    public GenericContext(
        IEnumerable<ITypeParameter>? classTypeParameters,
        IEnumerable<ITypeParameter>? methodTypeParameters)
    { ... }
}

// 使用：在方法编译上下文中解析泛型参数
var genericContext = new GenericContext(
    classTypeParameters: typeDef.TypeParameters,
    methodTypeParameters: method.TypeParameters);
```

---

## 六、MetadataFile 子类体系

```
MetadataFile (抽象基类)
├── PEFile            ★ 标准 PE 文件 (.dll/.exe)
│   ├── PEReader
│   └── MetadataReader
├── WebCilFile        WebCil 格式文件
└── ExportedTypeMetadata  导出类型元数据
```

关键元数据查询方法：

```csharp
public abstract class MetadataFile
{
    public MetadataReader Metadata { get; }
    public abstract string FileName { get; }
    public abstract TargetRuntime TargetRuntime { get; }

    // 方法体读取
    public MethodBodyBlock GetMethodBody(int rva);
    public abstract bool IsGacAssembly(string fullAssemblyName);
    public abstract ImmutableArray<Resource> GetResources();
    public abstract AssemblyDefinition GetAssemblyDefinition();
    // ... 更多查询
}
```

---

## 实战参考

- [TypeSystem/IType.cs](../ICSharpCode.Decompiler/TypeSystem/IType.cs) — IType 接口定义
- [TypeSystem/Implementation/MetadataModule.cs](../ICSharpCode.Decompiler/TypeSystem/Implementation/MetadataModule.cs) — 模块实现
- [TypeSystem/DecompilerTypeSystem.cs](../ICSharpCode.Decompiler/TypeSystem/DecompilerTypeSystem.cs) — 类型系统根
- [Metadata/PEFile.cs](../ICSharpCode.Decompiler/Metadata/PEFile.cs) — PE 文件封装
- [ILSpyX/FileLoaders/](../ICSharpCode.ILSpyX/FileLoaders/) — 文件加载器