# ILSpy IL 层架构剖析

> 职责：IL 中间表示层 — ILReader 字节码解码 · ILAst 指令体系 · IL Transform 管道（60+ 步）

---

## 数据流视角

```
原始 IL 字节码 (MethodBodyBlock)
  → ILReader.ReadIL()                                   ← 本章起点
    → 栈模拟 (ImmutableStack<ILVariable>)
    → 控制流图构建 (ImportBlock + CFG)
    → ILFunction (ILAst 根对象)
  → IL Transforms (60+ 步)                              ← 本章重点
    → BlockILTransform / StatementTransform
  → 结构化 ILAst
    → StatementBuilder.Convert()                        → (转入 04-csharp-ast)
```

---

## 一、ILReader — 字节码到 ILAst

### 1.1 核心流程

```csharp
// ILReader 读取方法体，返回 ILAst
public ILFunction ReadIL(
    MethodDefinitionHandle methodHandle,
    MethodBodyBlock body,            // 原始 IL 字节码块
    GenericContext genericContext,   // 泛型上下文
    ILFunctionKind kind,             // TopLevelFunction / Iterator / ...
    CancellationToken cancellationToken)
{
    // 1. 创建函数容器
    var function = new ILFunction(...);

    // 2. 构建控制流图（CFG）
    //    - 从字节码分割基本块
    //    - 通过栈模拟追踪类型流
    //    - 合并分支处的栈状态
    var cfg = BuildControlFlowGraph(body);

    // 3. 解码每个基本块的指令
    foreach (var block in cfg.Blocks)
        DecodeInstructions(block);

    // 4. 构建异常处理区域
    AttachExceptionHandlers(function, body);

    return function;
}
```

### 1.2 栈模拟

IL 是栈式虚拟机，ILReader 在解码时模拟栈操作：

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
        // 如果类型不兼容则创建新的临时局部变量
        // 返回 true 表示栈状态变化，需要重新导入
    }
}
```

---

## 二、ILAst 核心类型

### 2.1 继承层次

```
ILInstruction (抽象基类)
├── ILFunction             ★ 函数（局部变量 + 异常处理 + 调试信息）
├── Block                   ★ 基本块（有序指令集合）
├── BlockContainer          ★ 函数体容器（EntryPoint → Block）
├── IfInstruction           条件分支 (if-then-else)
├── SwitchInstruction       多路分支 (switch)
├── TryInstruction          try/catch/finally
├── LockInstruction         lock 语句
├── UsingInstruction        using 语句
├── Branch                  ★ 无条件/条件跳转
├── Leave                   ★ leave (离开 try/catch 区域)
├── StLoc                   ★ 局部变量存储
├── CallInstruction         ★ 方法调用
├── CallIndirect            间接调用 (函数指针/委托)
├── Comp                    比较指令
├── Conv                    类型转换
├── Await                   await 表达式
├── CompoundAssignmentInstruction  复合赋值 (x += y)
├── NullCoalescingInstruction      ?? 运算符
└── ... (40+ 指令类型)
```

### 2.2 关键指令详解

```csharp
// ILInstruction — 所有指令的基类
public abstract class ILInstruction
{
    public int StartILOffset { get; }       // 原始 IL 起始偏移
    public int EndILOffset { get; }         // 原始 IL 结束偏移
    public StackType ResultType { get; }    // 指令结果栈类型
    public InstructionFlags Flags { get; }  // 指令标志
    public IEnumerable<ILInstruction> Children { get; }  // 子指令
}

// Block — 基本块（有序指令集合）
public class Block : ILInstruction
{
    public BlockKind Kind { get; set; }     // ControlFlow / CallFinally / ...
    public InstructionCollection<ILInstruction> Instructions { get; }
    public IReadOnlyList<ILFunction>? Ancestors { get; }  // 词法封闭函数
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
}
```

### 2.3 ILVariable — 局部变量

```csharp
public class ILVariable
{
    public string? Name { get; set; }            // 名称（可能为 null）
    public int Index { get; }                    // 局部变量索引
    public int? IndexInMethodBody { get; }       // 方法体中的索引
    public StackType StackType { get; }          // 栈类型
    public IType? Type { get; set; }             // 具体类型
    public ILVariableKind Kind { get; }          // Local/Parameter/Exception...
    public bool HasGeneratedName { get; }        // 编译器生成名称
    public bool IsSingleDefinition { get; }      // SSA: 单一定值
    public IReadOnlyList<ILInstruction> StoreInstructions { get; }  // 所有赋值
}
```

---

## 三、IL Transform 管道 (60+ 步)

### 3.1 接口与上下文

```csharp
// IL/Transforms/IILTransform.cs
public interface IILTransform
{
    void Run(ILFunction function, ILTransformContext context);
}

public class ILTransformContext
{
    public IDecompilerTypeSystem TypeSystem { get; }
    public DecompilerSettings Settings { get; }
    public IDebugInfoProvider? DebugInfo { get; }
    public CancellationToken CancellationToken { get; }
    public Stepper? Stepper { get; }
}
```

### 3.2 Transform 分类总览

```
┌──────────────────────────────────────────────────────────────────┐
│                  IL Transform 管道全景                              │
├──────────────────────┬──────────────────────┬───────────────────┤
│ 控制流重构            │ 表达式识别             │ 模式识别           │
├──────────────────────┼──────────────────────┼───────────────────┤
│ ControlFlowSimp.     │ ILInlining             │ LoopDetection     │
│ SplitVariables       │ ExpressionTransforms   │ SwitchDetection   │
│ RemoveInfeasiblePath │ CopyPropagation        │ ConditionDetect.  │
│ DetectPinnedRegions  │ StatementTransform     │ AsyncAwaitDec.    │
│ DetectExitPoints     │ TransformAssignment    │ YieldReturnDec.   │
├──────────────────────┼──────────────────────┼───────────────────┤
│ 语言特性               │ 清理与规范化           │ 变量管理           │
├──────────────────────┼──────────────────────┼───────────────────┤
│ LockTransform         │ ReduceNestingTrans.   │ AssignVariable.   │
│ UsingTransform        │ ExpandNestedCond.     │ RemoveDeadVar.    │
│ NullCoalescingTrans.  │ FixRemainingIncr.     │ InlineReturnTrans.│
│ NullPropagationTrans. │ CombineExitsTrans.    │ IntroduceDynamic. │
│ DeconstructionTrans.  │ DelegateConstruct.    │ IntroduceNative.  │
│ TupleTransform        │ ProxyCallReplacer     │ IntroduceScoped.  │
└──────────────────────┴──────────────────────┴───────────────────┘
```

### 3.3 完整 Transform 序列

ILSpy 的 `CSharpDecompiler.GetILTransforms()` 定义了完整的 IL 变换序列：

```csharp
public static List<IILTransform> GetILTransforms()
{
    return new List<IILTransform> {
        // === 第 1 阶段：初始清理 ===
        new ControlFlowSimplification(),       // 简化控制流
        new SplitVariables(),                   // 拆分变量（SSA 化）
        new ILInlining(),                       // 内联短序列
        new InlineReturnTransform(),           // 内联 return
        new RemoveInfeasiblePathTransform(),   // 移除不可达路径

        // === 第 2 阶段：高级模式识别 ===
        new DetectPinnedRegions(),              // 固定区域
        new YieldReturnDecompiler(),            // yield return 识别
        new AsyncAwaitDecompiler(),             // async/await 识别
        new DetectCatchWhenConditionBlocks(),   // catch when 条件
        new DetectExitPoints(),                 // 出口点分析

        // === 第 3 阶段：表达式变换 ===
        new EarlyExpressionTransforms(),        // 早期表达式变换
        new SplitVariables(),                   // 再次拆分
        new RemoveDeadVariableInit(),           // 移除死变量初始化
        new ControlFlowSimplification(),        // 再次简化

        // === 第 4 阶段：结构化检测 ===
        new DynamicCallSiteTransform(),         // dynamic 调用点
        new SwitchDetection(),                  // switch 检测
        new SwitchOnStringTransform(),          // string switch
        new SwitchOnNullableTransform(),        // nullable switch
        new SplitVariables(),                   // 再次拆分

        // === 第 5 阶段：循环与条件 ===
        new BlockILTransform {                  // 循环检测
            PostOrderTransforms = { new LoopDetection() }
        },
        new DetectExitPoints(),                 // 再次分析出口

        // === 第 6 阶段：模式匹配变换 ===
        new PatternMatchingTransform(),

        // === 第 7 阶段：核心语句变换（内联+表达式+赋值+可空+内插...）===
        new BlockILTransform {
            PostOrderTransforms = {
                new ConditionDetection(),
                new LockTransform(),
                new UsingTransform(),
                new CachedDelegateInitialization(),
                new CachedReadOnlySpanInitialization(),
                new StatementTransform(
                    new ILInlining(),
                    new ExpressionTransforms(),
                    new DynamicIsEventAssignmentTransform(),
                    new TransformAssignment(),
                    new NullCoalescingTransform(),
                    new NullPropagationStatementTransform(),
                    new TransformArrayInitializers(),
                    new TransformCollectionAndObjectInitializers(),
                    new TransformExpressionTrees(),
                    new IndexRangeTransform(),
                    new DeconstructionTransform(),
                    new NamedArgumentTransform(),
                    new UserDefinedLogicTransform(),
                    new InterpolatedStringTransform()
                ),
            }
        },

        // === 第 8 阶段：后期清理 ===
        new ProxyCallReplacer(),
        new FixRemainingIncrements(),
        new CopyPropagation(),
        new DelegateConstruction(),
        new LocalFunctionDecompiler(),
        new TransformDisplayClassUsage(),
        new HighLevelLoopTransform(),
        new ReduceNestingTransform(),
        new RemoveRedundantReturn(),
        new IntroduceDynamicTypeOnLocals(),
        new IntroduceNativeIntTypeOnLocals(),
        new IntroduceScopedModifierOnLocals(),
        new ExpandNestedConditionals(),
        new AssignVariableNames(),              // 变量命名（最后一步）
    };
}
```

### 3.4 关键 Transform 说明

**ControlFlowSimplification** — 控制流简化。移除不必要的跳转，合并连续基本块。

**SplitVariables** — SSA 式变量拆分。将一个被多次赋值的变量拆分为多个只被赋值一次的变量。

**ILInlining** — 指令内联。将短基本块内联到使用点。

**LoopDetection** — 循环检测。识别 while/for/foreach/do-while 结构。

**ConditionDetection** — 条件检测。构建 if-else 链和 switch 语句。

**AsyncAwaitDecompiler** — async 状态机反编译。识别编译器生成的 `<M>d__N` 类型并还原 async/await 语法。

**YieldReturnDecompiler** — yield 枚举器反编译。识别 MoveNext / Current 模式还原 yield return。

**StatementTransform** — 关键复合变换。在语句级别内交错运行多个子变换，互相触发重新运行：

```
StatementTransform 内部循环:
  ILInlining             → 内联 → 触发重跑
  ExpressionTransforms   → 表达式变换 → 触发重跑
  TransformAssignment    → 赋值变换 (x = y, x += y)
  NullCoalescingTransform → ?? 运算符
  NullPropagationTransform → ?. 运算符
  TransformArrayInitializers → 数组初始化器
  TransformCollectionAndObjectInitializers → 集合/对象初始化器
  TransformExpressionTrees → 表达式树
  IndexRangeTransform    → 索引/范围 (^1, ..)
  DeconstructionTransform → 解构
  NamedArgumentTransform → 命名参数
  UserDefinedLogicTransform → 用户自定义逻辑运算符 (true/false)
  InterpolatedStringTransform → 内插字符串 ($"...")
```

---

## 四、BlockILTransform 模式

```csharp
public class BlockILTransform : IILTransform
{
    public List<IILTransform> PostOrderTransforms { get; } = new();

    public void Run(ILFunction function, ILTransformContext context)
    {
        // 后序遍历所有 Block，在每个 Block 上运行子 Transforms
        foreach (var block in function.Descendants.OfType<Block>())
        {
            foreach (var transform in PostOrderTransforms)
                transform.Run(block, context);
        }
    }
}
```

这个模式用于需要在每个 Block 级别运行的变换（如循环检测、条件检测），先处理后序遍历的子树再处理当前块。

---

## 五、ILAst 到 C# 的边界

IL Transform 管道的输出是**结构化的 ILAst**（循环、条件、switch 等高级结构已被识别），随后交给 `StatementBuilder`：

```csharp
// StatementBuilder 将 ILAst 块转换为 C# Statement
internal sealed class StatementBuilder : ILVisitor<TranslatedStatement>
{
    // Convert(ILInstruction) → Statement
    //   Block → BlockStatement
    //   IfInstruction → IfElseStatement
    //   SwitchInstruction → SwitchStatement
    //   StLoc + CallInstruction → ExpressionStatement(VariableDeclaration)
    //   ...
}
```

> 下一步：[04-csharp-ast.md](04-csharp-ast.md) — StatementBuilder / ExpressionBuilder / C# AST

---

## 实战参考

- [IL/ILReader.cs](../ICSharpCode.Decompiler/IL/ILReader.cs) — ILReader 实现
- [IL/ILInstruction.cs](../ICSharpCode.Decompiler/IL/ILInstruction.cs) — ILInstruction 基类
- [IL/ILFunction.cs](../ICSharpCode.Decompiler/IL/ILFunction.cs) — ILFunction 定义
- [IL/Transforms/](../ICSharpCode.Decompiler/IL/Transforms/) — 全部 IL Transforms
- [CSharp/CSharpDecompiler.cs](../ICSharpCode.Decompiler/CSharp/CSharpDecompiler.cs) — GetILTransforms() 完整列表

使用 `ilspycmd --ilast` 可查看 IL Transform 管道输出，`--after-transform <index>` 可在任意步骤停止。