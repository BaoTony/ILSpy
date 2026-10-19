# ILSpy IL Transform 管道

> 职责：IL 中间表示层后半 — IL Transform 管道（60+ 步）· 控制流重构 · 模式识别 · 变量与表达式变换

---

## 数据流视角

```
ILFunction (ILReader 输出)
  → IL Transforms (60+ 步)                              ← 本章重点
    → BlockILTransform / StatementTransform
    → 内联 / 循环检测 / async 识别 / 变量命名...
  → 结构化 ILAst
    → StatementBuilder.Convert()                        → 转入 06-csharp-output
```

---

## 一、Transform 接口与上下文

### 1.1 IILTransform 接口

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

每个 Transform 接收一个 `ILFunction` 和运行时上下文，在同一函数上完成变换后交给下一个 Transform。

### 1.2 BlockILTransform — 后序遍历

`BlockILTransform` 是调用频率最高的 Transform 包装器，它按后序遍历（先子块后父块）处理函数中所有 Block：

```csharp
// 使用示例：将循环检测逻辑注入 BlockILTransform
new BlockILTransform {
    PostOrderTransforms = {
        new ConditionDetection(),
        new LockTransform(),
        new UsingTransform(),
    }
}
```

后序遍历确保子块内的变换完成后才处理父块，避免重复工作。

### 1.3 StatementTransform — 重新运行机制

`StatementTransform` 是一个特殊的复合 Transform，内部多个子 Transform 会**反复运行**直到收敛：

```csharp
new StatementTransform(
    new ILInlining(),               // 内联变量
    new ExpressionTransforms(),     // 表达式折叠
    new TransformAssignment(),      // 赋值模式
    new NullCoalescingTransform(), // ?? 运算符
    // ... 子 Transform 通过 RequestRerun() 触发重新运行
)
```

机制：每当一个子 Transform 做了有意义的变更，它调用 `RequestRerun()`，`StatementTransform` 会在当前轮次结束后重新运行整条链。这保证了交错优化机会不会被遗漏。

---

## 二、Transform 分类

```
┌──────────────────────────────────────────────────────────────────┐
│                  IL Transform 管道全景（60+ 步）                     │
├──────────────────────┬──────────────────────┬───────────────────┤
│ 控制流重构            │ 表达式识别             │ 模式识别           │
├──────────────────────┼──────────────────────┼───────────────────┤
│ ControlFlowSimpli.   │ ILInlining             │ LoopDetection     │
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
│ NullPropagationTrans. │ CombineExitsTrans.    │ IntroduceDynamic.  │
│ DeconstructionTrans.  │ DelegateConstruct.    │ IntroduceNative.  │
│ TupleTransform        │ ProxyCallReplacer     │ IntroduceScoped.  │
└──────────────────────┴──────────────────────┴───────────────────┘
```

---

## 三、完整 Transform 序列

`CSharpDecompiler.GetILTransforms()` 定义了完整的运行次序（简化版）：

```
=== 第 1 阶段：初始清理（变量拆分 + 内联） ===
ControlFlowSimplification  →  合并相邻块 / 消除死跳转
SplitVariables             →  拆分变量为 SSA 形式
ILInlining                 →  内联短序列（仅使用一次的小变量）
InlineReturnTransform      →  内联 return 后的无意义指令
RemoveInfeasiblePathTransform → 移除不可达路径

=== 第 2 阶段：高级模式识别 ===
DetectPinnedRegions        →  fixed/stackalloc 固定区域
YieldReturnDecompiler      →  yield return 迭代器模式
AsyncAwaitDecompiler       →  async/await 状态机模式
DetectCatchWhenBlocks     →  catch when 条件块
DetectExitPoints           →  出口点分析

=== 第 3 阶段：表达式变换 ===
EarlyExpressionTransforms  →  早期表达式折叠
SplitVariables             →  再次拆分（新发现的变量）
RemoveDeadVariableInit     →  移除死变量初始化
ControlFlowSimplification  →  再次简化

=== 第 4 阶段：结构化分支检测 ===
DynamicCallSiteTransform   →  dynamic 调用点
SwitchDetection            →  switch 表/跳转表检测
SwitchOnStringTransform    →  string switch 检测
SwitchOnNullableTransform  →  nullable switch 检测
SplitVariables             →  再次拆分

=== 第 5 阶段：循环检测 ===
BlockILTransform(LoopDetection) → 在 BlockILTransform 中运行循环检测

=== 第 6 阶段：模式匹配变换 ===
PatternMatchingTransform   →  模式匹配语法识别

=== 第 7 阶段：核心语句变换 ===
BlockILTransform {
    ConditionDetection       →  条件检测 (if/else)
    LockTransform            →  lock 语句
    UsingTransform           →  using 语句
    CachedDelegateInit.      →  缓存委托初始化
    StatementTransform {
        ILInlining            →  内联
        ExpressionTransforms  →  表达式折叠
        TransformAssignment   →  赋值变换
        NullCoalescing        →  ?? 运算符
        NullPropagation       →  ?. 运算符
        ArrayInitializers     →  数组初始化器
        CollectionInit.       →  集合/对象初始化器
        ExpressionTrees       →  表达式树
        IndexRange            →  索引/范围
        Deconstruction        →  解构
        NamedArgument         →  命名参数
        UserDefinedLogic      →  用户自定义逻辑
        InterpolatedString    →  内插字符串
    }
}

=== 第 8 阶段：后期清理 ===
ProxyCallReplacer          →  代理调用替换
FixRemainingIncrements     →  修复剩余的增量运算
CopyPropagation            →  拷贝传播
DelegateConstruction       →  委托构造
LocalFunctionDecompiler    →  局部函数反编译
TransformDisplayClassUsage →  lambda 闭包类处理
HighLevelLoopTransform     →  高层循环变换
ReduceNestingTransform     →  减少嵌套
RemoveRedundantReturn      →  移除冗余 return
IntroduceDynamicTypeOnLocals    →  dynamic 类型注解
IntroduceNativeIntTypeOnLocals  →  nint/nuint 类型注解
IntroduceScopedModifier          →  scoped 修饰符
ExpandNestedConditionals   →  展开嵌套条件
AssignVariableNames        →  ★ 变量命名（最后一步）
```

> 实际序列可能因版本变更略有调整，以 `CSharpDecompiler.cs` 中的 `GetILTransforms()` 为准。

---

## 四、典型 Transform 详解

### 4.1 SplitVariables — SSA 化

将 IL 栈变量拆分为单一定值（SSA）形式，使后续分析可以精确追踪变量流向：

```csharp
// 拆分前：
//   V_0 ← 5
//   V_0 ← V_0 + 1     // V_0 有两处定值
//
// 拆分后：
//   V_0 ← 5
//   V_1 ← V_0 + 1     // 每个定值对应唯一变量
```

### 4.2 ILInlining — 内联

将仅使用一次且无副作用的变量替换为其定义表达式：

```csharp
// 内联前：                    // 内联后：
// stloc V_0(ldloc V_a)       // (消除)
// ... 仅使用一次 V_0 ...
// ldloc V_0  →  直接替换为 ldloc V_a
```

### 4.3 AsyncAwaitDecompiler

将 C# 编译器生成的 async 状态机模式还原为 async/await 语法。识别特征：

- 状态机类（`IAsyncStateMachine` 实现）
- `MoveNext()` 方法中的状态切换（状态号 → switch 分支）
- `awaiter.GetResult()` 调用模式

### 4.4 YieldReturnDecompiler

类似地还原 yield return 迭代器模式。关键识别：

- `IEnumerable<T>` / `IEnumerator<T>` 的编译器生成类
- 状态机的 `<>2__current` 字段映射为 yield return 值
- `<>1__state` 的状态值对应 yield break / 各 yield return 点

---

## 实战参考

- [IL/Transforms/IILTransform.cs](../ICSharpCode.Decompiler/IL/Transforms/IILTransform.cs) — Transform 接口
- [IL/Transforms/ILInlining.cs](../ICSharpCode.Decompiler/IL/Transforms/ILInlining.cs) — 内联
- [IL/Transforms/SplitVariables.cs](../ICSharpCode.Decompiler/IL/Transforms/SplitVariables.cs) — SSA 变量拆分
- [IL/Transforms/StatementTransform.cs](../ICSharpCode.Decompiler/IL/Transforms/StatementTransform.cs) — 复合 Transform
- [IL/ControlFlow/AsyncAwaitDecompiler.cs](../ICSharpCode.Decompiler/IL/ControlFlow/AsyncAwaitDecompiler.cs) — async/await
- [IL/ControlFlow/YieldReturnDecompiler.cs](../ICSharpCode.Decompiler/IL/ControlFlow/YieldReturnDecompiler.cs) — yield return
- [CSharp/CSharpDecompiler.cs](../ICSharpCode.Decompiler/CSharp/CSharpDecompiler.cs) — GetILTransforms() 完整序列