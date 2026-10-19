# ILSpy IL 字节码读取与 ILAst

> 职责：IL 中间表示层前半 — ILReader 字节码解码 · ILAst 指令体系 · 控制流与变量表示

---

## 数据流视角

```
原始 IL 字节码 (MethodBodyBlock)
  → ILReader.ReadIL()                                   ← 本章起点
    → 栈模拟 (ImmutableStack<ILVariable>)
    → 控制流图构建 (ImportBlock + CFG)
    → ILFunction (ILAst 根对象)
  → IL Transforms (60+ 步)                              → 转入 04-il-transforms
```

---

## 一、ILReader — 字节码到 ILAst

### 1.1 核心流程

ILReader 从 `System.Reflection.Metadata.MethodBodyBlock` 读取原始 IL 字节码，构建 ILSpy 自己的 ILAst 中间表示：

```csharp
// IL/ILReader.cs
public ILFunction ReadIL(
    MethodDefinitionHandle methodHandle,
    MethodBodyBlock body,
    GenericContext genericContext,
    ILFunctionKind kind,
    CancellationToken cancellationToken)
{
    // 1. 创建函数容器
    var function = new ILFunction(...);

    // 2. 构建控制流图（CFG）
    //    - 从字节码分割基本块（通过跳转目标/异常处理边界）
    //    - 通过栈模拟追踪类型流
    //    - 合并分支处的栈状态
    var cfg = BuildControlFlowGraph(body);

    // 3. 解码每个基本块的 IL 指令
    foreach (var block in cfg.Blocks)
        DecodeInstructions(block);

    // 4. 构建异常处理区域（try/catch/finally/filter）
    AttachExceptionHandlers(function, body);

    return function;
}
```

### 1.2 栈模拟机制

IL 是栈式虚拟机，ILReader 在解码时必须模拟栈操作才能追踪类型流向：

```csharp
// ILReader 内部维护每个基本块的栈状态
private sealed class ImportedBlock
{
    public Block Block;                              // 对应的 ILAst 块
    public ImmutableStack<ILVariable> InputStack;    // 入口栈状态
    public List<(ImportedBlock, ImmutableStack<ILVariable>)> OutgoingEdges;

    // 当新边到达时，合并栈类型
    public bool MergeStackTypes(ImmutableStack<ILVariable> newEdge)
    {
        // 如果同一位置有不同变量，创建临时局部变量统一表示
        // 返回 true 表示栈状态变化，需要重新导入该块及其后继
    }
}
```

关键点：栈模拟不是直接模拟值，而是模拟**变量引用**。每个栈槽位映射为一个 `ILVariable`，后续通过变量分析（`SplitVariables`、`CopyPropagation` 等 Transform）还原真实的局部变量语义。

---

## 二、ILAst 核心类型

### 2.1 继承层次

```
ILInstruction (抽象基类)
├── ILFunction             ★ 函数容器（局部变量 + 异常处理 + 调试信息）
├── Block                   ★ 基本块（有序指令集合）
├── BlockContainer          ★ 函数体容器（EntryPoint → Block）
│
├── 分支与控制流
│   ├── IfInstruction       条件分支 (if-then-else)
│   ├── SwitchInstruction   多路分支 (switch)
│   ├── Branch              ★ 无条件/条件跳转
│   ├── Leave               leave (离开 try/catch 区域)
│   ├── TryInstruction      try/catch/finally
│   ├── LockInstruction     lock 语句
│   └── UsingInstruction    using 语句
│
├── 调用
│   ├── CallInstruction     ★ 方法调用
│   ├── CallIndirect        间接调用 (函数指针/委托)
│   └── NewObj              对象构造 (new)
│
├── 存储与加载
│   ├── StLoc               ★ 局部变量存储
│   ├── LdLoc               局部变量加载
│   ├── LdLoca              局部变量地址加载
│   ├── StObj               对象存储
│   └── LdObj               对象加载
│
├── 运算与转换
│   ├── Comp                比较指令
│   ├── Conv                类型转换
│   ├── CompoundAssignmentInstruction 复合赋值 (x += y)
│   ├── NullCoalescingInstruction     ?? 运算符
│   └── BinaryNumericInstruction     二元数值运算
│
├── C# 语义
│   ├── Await               await 表达式
│   ├── AddressOf           取地址 (&)
│   └── DefaultValue        默认值 (default(T))
│
└── 其他 (40+ 指令类型)
```

### 2.2 关键数据结构

```csharp
// ILInstruction — 所有指令的基类
public abstract class ILInstruction
{
    public int StartILOffset { get; }       // 原始 IL 字节偏移
    public int EndILOffset { get; }
    public StackType ResultType { get; }    // 指令结果栈类型
    public InstructionFlags Flags { get; }  // 指令标志
    public IEnumerable<ILInstruction> Children { get; }  // 子指令
}

// Block — 基本块（有序指令集合）
public class Block : ILInstruction
{
    public BlockKind Kind { get; set; }     // ControlFlow / CallFinally / ...
    public InstructionCollection<ILInstruction> Instructions { get; }
    public IReadOnlyList<ILFunction>? Ancestors { get; }  // 词法封闭函数（闭包/lambda）
}

// BlockContainer — 函数体容器
public class BlockContainer : ILInstruction
{
    public Block EntryPoint { get; set; }   // ★ 入口块
    public ILFunction? Parent { get; }
}

// ILFunction — 函数
public class ILFunction
{
    public ILVariableCollection Variables { get; }
    public BlockContainer? Body { get; }
    public bool IsAsync { get; }
    public bool IsIterator { get; }
    public IMethod? Method { get; }
    public MethodBodyBlock? MethodBody { get; }
    public List<ExceptionHandler> ExceptionHandlers { get; }
    public List<ILLocalFunction> LocalFunctions { get; }
}
```

### 2.3 ILVariable — 局部变量

```csharp
public class ILVariable
{
    public string? Name { get; set; }            // 变量名（可能为 null）
    public int Index { get; }                    // 局部变量索引
    public int? IndexInMethodBody { get; }       // 方法体中的索引
    public StackType StackType { get; }          // 栈类型（I4/I8/R4/R8/O/Ref/...）
    public IType? Type { get; set; }             // 具体类型（推断后）
    public ILVariableKind Kind { get; }          // Local/Parameter/Exception/...
    public bool HasGeneratedName { get; }        // 编译器生成名称
    public bool IsSingleDefinition { get; }      // SSA: 单一定值
    public IReadOnlyList<ILInstruction> StoreInstructions { get; }  // 所有赋值指令
}
```

`StackType` 枚举区分 IL 层面的类型：

```
StackType.I4   (int32)         StackType.I8   (int64)
StackType.I    (native int)    StackType.F4   (float32)
StackType.F8   (float64)       StackType.O    (object reference)
StackType.Ref  (managed pointer) StackType.ValueType
```

---

## 三、控制流块管理

### 3.1 Block 的三种角色

一个 `Block` 可以担任三种角色：

| BlockKind | 含义 |
|---|---|
| `ControlFlow` | 普通控制流块 |
| `CallFinally` | finally 子句的入口块 |
| `CallCleanup` | using/fixed 等资源的清理块 |

### 3.2 异常处理

```csharp
// BlockContainer 和异常处理器的关系
// 每个异常处理器定义一段受保护的代码区域：
public class ExceptionHandler
{
    public Block? TryBlock;
    public Block? FilterBlock;   // when 子句
    public Block? HandlerBlock;  // catch 体
    public Block? FinallyBlock;
    public IType? CatchType;     // 捕获的异常类型
}
```

异常处理在 ILAst 中使用专用指令：

- `TryInstruction`：包装 try/catch，子指令分别为 try 体块、catch 体块和 finally 体块
- `Leave`：在 try/catch 内部跳出受保护区域到指定目标
- `Branch`：条件/无条件跳转

---

## 实战参考

- [IL/ILReader.cs](../ICSharpCode.Decompiler/IL/ILReader.cs) — IL 字节码读取器
- [IL/ILInstruction.cs](../ICSharpCode.Decompiler/IL/ILInstruction.cs) — 指令基类
- [IL/ILFunction.cs](../ICSharpCode.Decompiler/IL/ILFunction.cs) — 函数级 ILAst
- [IL/ILVariable.cs](../ICSharpCode.Decompiler/IL/ILVariable.cs) — 局部变量
- [IL/Instructions/](../ICSharpCode.Decompiler/IL/Instructions/) — 具体指令类
- [IL/StackType.cs](../ICSharpCode.Decompiler/IL/StackType.cs) — 栈类型枚举
- [IL/Block.cs](../ICSharpCode.Decompiler/IL/Block.cs) — 基本块
- [IL/BlockContainer.cs](../ICSharpCode.Decompiler/IL/BlockContainer.cs) — 函数体容器