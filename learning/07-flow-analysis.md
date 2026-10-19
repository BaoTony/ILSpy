# ILSpy 数据流分析框架

> 职责：控制流图 + 数据流分析引擎 — ControlFlowNode · DataFlowVisitor · 定值分析 · 支配树 · 到达定义

---

## 一、概述

`ICSharpCode.Decompiler.FlowAnalysis` 命名空间提供了一组通用的控制流与数据流分析工具。这些工具不直接面向反编译输出，而是被 IL Transform 管道在内部使用（如 `CopyPropagation`、`SplitVariables`、`DetectExitPoints` 等需要分析变量流向和控制流结构的 Transform）。

核心组成（5 个文件）：

```
FlowAnalysis/
├── ControlFlowNode.cs           ★ 控制流图节点
├── DataFlowVisitor.cs           ★ 数据流分析引擎（格/不动点）
├── DefiniteAssignmentVisitor.cs  定值分析
├── ReachingDefinitionsVisitor.cs 到达定义分析
└── Dominance.cs                  支配树（Cooper-Harvey-Kennedy）
```

---

## 二、ControlFlowNode — 控制流图

### 2.1 节点结构

```csharp
public class ControlFlowNode
{
    public int UserIndex;                 // 可在数组中查找附加信息
    public object? UserData;
    public bool Visited;                   // 各种算法中使用的标记
    public int PostOrderNumber;            // 后序遍历编号（支配分析时计算）

    // 支配树
    public ControlFlowNode? ImmediateDominator;       // 直接支配者
    public List<ControlFlowNode>? DominatorTreeChildren; // 支配树子节点
    public bool IsReachable => DominatorTreeChildren != null;

    // 控制流边
    public List<ControlFlowNode> Predecessors;  // 入边
    public List<ControlFlowNode> Successors;    // 出边
}
```

每个 `ControlFlowNode` 代表控制流图中的一个基本块。

### 2.2 基本块划分

控制流图的构建在 `ILReader` 阶段完成：以跳转目标、异常处理器边界为分割点将 IL 字节码切分为基本块。

---

## 三、DataFlowVisitor — 数据流分析引擎

### 3.1 设计原理

`DataFlowVisitor<State>` 是一个**泛型不动点迭代引擎**，基于格（lattice）理论实现经典的数据流分析框架：

```
对每个控制流节点 n:
    state[n] = ⊥ (bottom = 无信息)

迭代直到不动点:
    对每条边 (pred → n):
        state[n] = state[n] ⊔ transfer(state[pred], n)
    // ⊔ = join 操作（最小上界）
```

### 3.2 IDataFlowState 接口

```csharp
public interface IDataFlowState<Self> where Self : IDataFlowState<Self>
{
    // 偏序关系：this 是否 ≤ otherState
    bool LessThanOrEqual(Self otherState);

    // 克隆当前状态（创建独立副本，用于分支点）
    Self Clone();

    // 原地替换为另一状态的内容
    void ReplaceWith(Self newContent);

    // 与外来状态做 join（取最小上界 = 合并信息）
    void JoinWith(Self incomingState);
}
```

状态必须形成**联合半格（join-semilattice）**且有**有限高度**（没有无限上升链 s₁ < s₂ < s₃ < ...），确保分析一定终止。

### 3.3 转换函数

对于每条 IL 指令，`DataFlowVisitor` 调用 `Visit*` 方法执行**转换函数**（transfer function），修改当前状态：

```csharp
// StLoc 的转换：标记该变量为"已定值"
protected virtual void VisitStLoc(StLoc inst)
{
    // 状态从"V_0 未赋值"变为"V_0 已赋值"
}
```

### 3.4 try/finally 的 Meet 操作

`finally` 块在所有退出路径上都会执行，因此 `finally` 末尾的状态需要与 try 块的出口状态做 **meet（最大下界）**。如果状态实现了 meet 操作，它就是一个**完整格**。

---

## 四、DefiniteAssignment — 定值分析

### 4.1 分析目标

确定在代码的每一点，哪些变量**一定已经被赋值过**。

```csharp
class DefiniteAssignmentVisitor : DataFlowVisitor<DefiniteAssignmentVisitor.State>
{
    public struct State : IDataFlowState<State>
    {
        readonly BitSet bits;
        // bits[i] = true 表示存在某条路径在到达该位置时，
        //           没有对 Variables[i] 赋值
        // 即：bits[i] = !definitelyAssigned(i)
        //
        // 初始状态：所有 bit 置 1（nothing is definitely assigned）
        // Bottom 状态：所有 bit 清 0（everything is definitely assigned）
    }
}
```

### 4.2 格结构

- **Bottom (⊥)**：全 0（所有变量都已定值）
- **Join 操作**：按位 AND（两边都定值才是定值）
- **转换**：`StLoc` 指令将其对应的 bit 清零

### 4.3 应用

定值分析用于：
- `SplitVariables`：判断是否可以安全拆分变量
- `RemoveDeadVariableInit`：移除从未使用过的变量初始化
- 确保输出代码中不会出现未赋值的变量引用

---

## 五、ReachingDefinitions — 到达定义分析

### 5.1 分析目标

对于每个变量，在代码每一点找出**哪些 store 指令可能定义了当前值**。

### 5.2 编码技巧

为节省内存，所有 store 指令按变量分组排序：同一变量的 stores 在 BitSet 中占据**连续区域**，这使得新 store 可以通过一次性批量清除来覆盖旧 store 的定义：

```
allStores 数组布局：
[ V_0_store1, V_0_store2 | V_1_store1, V_1_store2, V_1_store3 | ... ]
  ←  V_0 连续区段 →       ←  V_1 连续区段 →
```

当遇到对 V_0 的新 store 时，只需一次性 mask out V_0 的整个区段——所有旧的 V_0 定义同时失效。

### 5.3 边界限制

到达定义分析**不追踪** `LdLoca` / 引用 / 指针传播。对于 `AddressCount != 0` 的变量，分析结果可能不完整。

---

## 六、Dominance — 支配树

### 6.1 支配关系

节点 d **支配**节点 n 当且仅当：从入口点到 n 的所有路径都经过 d。

```
         [Entry]
        /   |   \
      [A]  [B]  [C]
       |    |
      [D]  [E]
        \  /
        [F]

支配关系：
  Entry 支配所有节点
  A 支配 D，B 支配 E
  Entry 支配 F（A、B、C 都不支配 F，因为有替代路径）
```

### 6.2 Cooper-Harvey-Kennedy 算法

ILSpy 使用"快速支配算法"：

```csharp
public static void ComputeDominance(ControlFlowNode entryPoint, CancellationToken ct)
{
    // 1. 后序遍历编号
    var nodes = entryPoint.TraversePostOrder(n => n.Successors);

    // 2. entryPoint 的支配者设为自己（算法初始化）
    entryPoint.ImmediateDominator = entryPoint;

    // 3. 迭代直到不动点（逆后序扫描）
    bool changed;
    do {
        changed = false;
        for (int i = nodes.Count - 2; i >= 0; i--) {
            ControlFlowNode b = nodes[i];
            ControlFlowNode? newIdom = null;
            foreach (var p in b.Predecessors) {
                if (p.ImmediateDominator != null) {
                    newIdom = newIdom == null ? p : Intersect(p, newIdom);
                }
            }
            if (b.ImmediateDominator != newIdom) {
                b.ImmediateDominator = newIdom;
                changed = true;
            }
        }
    } while (changed);

    // 4. 重置 entryPoint 的支配者为 null
    entryPoint.ImmediateDominator = null;

    // 5. 构建子节点列表（支配树）
    foreach (var node in nodes)
        node.ImmediateDominator?.DominatorTreeChildren?.Add(node);
}
```

### 6.3 应用

- **循环检测**：回边 n → d 满足 d dominates n（`LoopDetection` 依赖此特征）
- **变量拆分**：判断变量在分支合并点是否可以安全拆分
- **不可达代码消除**：`IsReachable` 字段

---

## 实战参考

- [FlowAnalysis/ControlFlowNode.cs](../ICSharpCode.Decompiler/FlowAnalysis/ControlFlowNode.cs) — 控制流图节点
- [FlowAnalysis/DataFlowVisitor.cs](../ICSharpCode.Decompiler/FlowAnalysis/DataFlowVisitor.cs) — 数据流分析引擎
- [FlowAnalysis/DefiniteAssignmentVisitor.cs](../ICSharpCode.Decompiler/FlowAnalysis/DefiniteAssignmentVisitor.cs) — 定值分析
- [FlowAnalysis/ReachingDefinitionsVisitor.cs](../ICSharpCode.Decompiler/FlowAnalysis/ReachingDefinitionsVisitor.cs) — 到达定义分析
- [FlowAnalysis/Dominance.cs](../ICSharpCode.Decompiler/FlowAnalysis/Dominance.cs) — 支配树