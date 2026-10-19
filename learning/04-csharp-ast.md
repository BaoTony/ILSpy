# ILSpy C# AST 与输出层

> 职责：C# 语法树层 — StatementBuilder/ExpressionBuilder · C# AST 节点体系 · AST Transform（14 步）· OutputVisitor 文本输出

---

## 数据流视角

```
结构化 ILAst (IL Transform 管道输出)
    ↓
StatementBuilder.Convert(ILInstruction)  → C# Statement   ← ILVisitor 模式
ExpressionBuilder.Translate(ILInstruction) → C# Expression
    ↓
C# SyntaxTree (TypeDeclaration → MethodDeclaration → BlockStatement → ...)
    ↓
AST Transforms (14 步)
    ├── PatternStatementTransform   (模式语句)
    ├── DeclareVariables            (声明变量)
    ├── FixNameCollisions           (修复命名冲突)
    └── AddXmlDocumentationTransform (XML 文档)
    ↓
CSharpOutputVisitor.VisitSyntaxTree(syntaxTree, tokenWriter)
    → InsertMissingTokensDecorator (补全分号/大括号)
    → InsertRequiredSpacesDecorator (自动空格)
    → TextWriterTokenWriter → string
```

---

## 一、C# AST 节点体系

### 1.1 树结构概览

```
SyntaxTree (根节点)
├── UsingDeclaration[]          using 语句
├── ExternAliasDeclaration[]    extern 别名
├── AttributeSection[]          程序集级 Attribute
├── NamespaceDeclaration        命名空间
│     └── TypeDeclaration       class/struct/interface/enum/delegate
│           ├── AttributeSection[]
│           ├── Constraint[]    泛型约束
│           ├── TypeParameterDeclaration[]
│           ├── MethodDeclaration           方法
│           │     ├── ParameterDeclaration[]
│           │     ├── AttributeSection[]
│           │     └── BlockStatement → ...  方法体
│           ├── PropertyDeclaration         属性
│           ├── FieldDeclaration            字段
│           ├── EventDeclaration            事件
│           ├── ConstructorDeclaration      构造函数
│           ├── OperatorDeclaration         运算符
│           ├── IndexerDeclaration          索引器
│           ├── DestructorDeclaration       析构函数
│           ├── EnumMemberDeclaration       枚举成员
│           └── TypeDeclaration             嵌套类型
```

### 1.2 核心基类

```csharp
// CSharp/Syntax/AstNode.cs
public abstract class AstNode : IAnnotatable
{
    public AstNode? Parent { get; }
    public AstNode? Role { get; }
    public AstNode? PrevSibling { get; }
    public AstNode? NextSibling { get; }
    public IEnumerable<AstNode> Children { get; }
    public TextLocation StartLocation { get; }
    public TextLocation EndLocation { get; }

    // 访问者模式
    public abstract void AcceptVisitor(IAstVisitor visitor);
    public abstract T AcceptVisitor<T>(IAstVisitor<T> visitor);

    // 克隆与替换
    public AstNode Clone();
    public AstNode ReplaceWith(AstNode newNode);

    // 注释（Annotation）
    public void AddAnnotation<T>(T annotation);
    public T? Annotation<T>();
}

// 关键派生路径：
// AstNode → EntityDeclaration → MethodDeclaration
// AstNode → Statement → BlockStatement
// AstNode → Expression → BinaryOperatorExpression
```

### 1.3 Expression（表达式）分类

```
Expression (抽象基类, ~45 种)
├── 基本表达式
│   ├── PrimitiveExpression      字面量 (42, "hello", true)
│   ├── NullReferenceExpression  null
│   ├── ThisReferenceExpression  this
│   ├── BaseReferenceExpression  base
│   └── IdentifierExpression     标识符引用
│
├── 调用与访问
│   ├── InvocationExpression     foo(args)
│   ├── MemberReferenceExpression a.b
│   ├── IndexerExpression        a[i]
│   ├── ObjectCreateExpression   new Foo()
│   └── AnonymousMethodExpression 匿名方法/Lambda
│
├── 运算符
│   ├── BinaryOperatorExpression a + b
│   ├── UnaryOperatorExpression  -a, !a
│   ├── AssignmentExpression     a = b
│   └── ConditionalExpression    a ? b : c
│
├── 类型操作
│   ├── CastExpression           (T)x
│   ├── AsExpression             x as T
│   ├── IsExpression             x is T
│   ├── TypeOfExpression         typeof(T)
│   ├── SizeOfExpression         sizeof(T)
│   └── DefaultValueExpression   default(T)
│
├── C# 模式
│   ├── InterpolatedStringExpression  $"hello {name}"
│   ├── SwitchExpression         x switch { ... }
│   ├── TupleExpression          (a, b)
│   ├── ThrowExpression          throw expr
│   ├── QueryExpression          from x in ys...
│   └── WithInitializerExpression  r with { A = 1 }
│
└── 其他
    ├── AnonymousTypeCreateExpression  new { A = 1 }
    ├── ArrayCreateExpression     new T[] { ... }
    ├── CheckedExpression         checked(expr)
    ├── DirectionExpression       ref x
    └── ...
```

### 1.4 Statement（语句）分类

```
Statement (抽象基类, ~30 种)
├── BlockStatement               { ... }         ★ 最常用
├── ExpressionStatement          expr;            ★ 表达式语句
├── VariableDeclarationStatement int x = 1;      ★ 变量声明
│
├── 条件
│   ├── IfElseStatement           if (c) { } else { }
│   └── SwitchStatement           switch (x) { }
│
├── 循环
│   ├── ForStatement              for (;;) { }
│   ├── ForeachStatement          foreach (var x in y) { }
│   ├── WhileStatement            while (c) { }
│   └── DoWhileStatement          do { } while (c);
│
├── 跳转
│   ├── ReturnStatement           return x;
│   ├── GotoStatement             goto label;
│   ├── BreakStatement            break;
│   ├── ContinueStatement         continue;
│   ├── YieldReturnStatement      yield return x;
│   └── YieldBreakStatement       yield break;
│
├── 异常
│   ├── TryCatchStatement         try { } catch { } finally { }
│   └── ThrowStatement            throw expr;
│
├── 资源管理
│   ├── UsingStatement            using (var x = ...) { }
│   ├── LockStatement             lock (x) { }
│   └── FixedStatement            fixed (T* p = ...) { }
│
└── 其他
    ├── CheckedStatement          checked { }
    ├── UncheckedStatement        unchecked { }
    ├── UnsafeStatement           unsafe { }
    └── LabelStatement            label:
```

---

## 二、StatementBuilder — ILAst → C# Statement

### 2.1 设计模式：ILVisitor

`StatementBuilder` 使用访问者模式将每种 IL 指令映射为 C# 语句：

```csharp
internal sealed class StatementBuilder : ILVisitor<TranslatedStatement>
{
    internal readonly ExpressionBuilder exprBuilder;

    // 主转换入口
    public Statement Convert(ILInstruction inst)
    {
        return inst.AcceptVisitor(this)?.ToStatement() ?? CreateErrorStatement();
    }

    // Block → BlockStatement
    protected internal override TranslatedStatement VisitBlock(Block block)
    {
        var stmts = new List<Statement>();
        foreach (var inst in block.Instructions)
            stmts.Add(Convert(inst));
        return TranslatedStatement.FromBlock(stmts.ToArray(), block);
    }

    // IfInstruction → IfElseStatement
    protected internal override TranslatedStatement VisitIfInstruction(IfInstruction inst)
    {
        var condition = exprBuilder.Translate(inst.Condition);
        var trueBlock = Convert(inst.TrueInst);
        var falseBlock = inst.FalseInst != null ? Convert(inst.FalseInst) : null;
        return new TranslatedStatement(
            new IfElseStatement { Condition = condition, ... });
    }

    // StLoc → VariableDeclarationStatement
    protected internal override TranslatedStatement VisitStLoc(StLoc inst)
    {
        var value = exprBuilder.Translate(inst.Value);
        // 判断是否首次赋值 → 变量声明
        if (ShouldDeclareWhileAssignment(inst.Variable))
            return DeclareVariable(inst.Variable, value);
        else
            return AssignVariable(inst.Variable, value);
    }
}
```

### 2.2 ExpressionBuilder — IL 指令 → C# Expression

```csharp
internal sealed class ExpressionBuilder
{
    // 核心翻译方法
    public Expression Translate(ILInstruction inst)
    {
        // 递归将 IL 指令转为 C# Expression
        switch (inst)
        {
            case CallInstruction call:
                // 方法调用 → InvocationExpression 或 BinaryOperatorExpression
                return TranslateCall(call);
            case Comp comp:
                // 比较 → BinaryOperatorExpression
                return TranslateComparison(comp);
            case LdLoc ldloc:
                // 加载局部变量 → IdentifierExpression
                return new IdentifierExpression(ldloc.Variable.Name);
            case Conv conv:
                // 类型转换 → CastExpression
                return new CastExpression(...);
            // ... 40+ 种指令
        }
    }

    // 方法调用翻译（最重要的部分之一）
    Expression TranslateCall(CallInstruction call)
    {
        var method = call.Method;

        // 运算符检测：op_Addition → a + b
        if (method.IsOperator && TryTranslateOperator(call, out var opExpr))
            return opExpr;

        // 属性访问检测：get_X → X
        if (IsPropertyAccessor(method, out var prop))
            return TranslatePropertyAccess(prop);

        // 默认：方法调用
        return new InvocationExpression(
            MakeMethodReference(method),
            call.Arguments.Select(Translate).ToList());
    }
}
```

---

## 三、AST Transform 管道 (14 步)

### 3.1 变换序列

```csharp
// CSharp/CSharpDecompiler.cs - GetAstTransforms()
public static List<IAstTransform> GetAstTransforms()
{
    return new List<IAstTransform> {
        new PatternStatementTransform(),              // 模式语句 → switch/if
        new RewriteVisualBasicWithEventsIn...(),      // VB WithEvents
        new ReplaceMethodCallsWithOperators(),        // 方法调用 → 运算符
        new IntroduceUnsafeModifier(),                // unsafe 修饰符
        new AddCheckedBlocks(),                       // checked { } 块

        new DeclareVariables(),                       // ★ 声明变量
        new TransformFieldAndConstructorInitializers(),// 字段/构造器初始化器
        new PrettifyAssignments(),                    // 美化赋值

        new IntroduceUsingDeclarations(),             // using 声明
        new IntroduceQueryExpressions(),              // ★ LINQ 查询表达式
        new CombineQueryExpressions(),                // 合并查询

        new NormalizeBlockStatements(),               // 规范化块语句
        new FlattenSwitchBlocks(),                    // 展平 switch

        new RenameVisualBasicAnonymousTypes(),        // VB 匿名类型重命名
        new FixNameCollisions(),                      // ★ 修复命名冲突

        new AddXmlDocumentationTransform(),           // XML 文档注释
    };
}
```

### 3.2 关键 Transform 说明

**DeclareVariables** — 变量声明。将 `int x; x = 5;` 合并为 `int x = 5;`，并确定变量的声明位置。

**IntroduceQueryExpressions** — LINQ 查询还原。将 `Enumerable.Select(Enumerable.Where(...))` 的链式调用还原为 `from x in xs where ... select ...` 语法。

**FixNameCollisions** — 命名冲突修复。当反编译出的变量名与已有成员名冲突时，自动重命名（如 `i` → `i1`）。

**AddXmlDocumentationTransform** — XML 文档。将 XML 文档注释附加到类型和成员上。

---

## 四、OutputVisitor — C# AST → 文本

### 4.1 输出管道

```
CSharpOutputVisitor (AstVisitor 实现)
    │
    ├── InsertMissingTokensDecorator    ★ 装饰器 1: 自动补分号/括号
    │     └── ITokenWriter
    │
    ├── InsertRequiredSpacesDecorator   ★ 装饰器 2: 自动空格
    │     └── ITokenWriter
    │
    └── TextWriterTokenWriter           ★ 最终写入 TextWriter
          └── StringWriter
```

### 4.2 ITokenWriter 接口

```csharp
// CSharp/OutputVisitor/ITokenWriter.cs
public interface ITokenWriter
{
    void StartNode(AstNode node);     // 进入节点
    void EndNode(AstNode node);       // 离开节点
    void WriteIdentifier(Identifier identifier);
    void WriteKeyword(Role role);     // class, void, public...
    void WriteToken(Role role);       // {, }, ;, ...
    void Space();
    void NewLine();
    void WriteComment(CommentType commentType, string content);
    void WritePreProcessorDirective(PreProcessorDirective directive);
    void Indent();
    void Unindent();
}
```

### 4.3 装饰器模式

装饰器链可以在不修改核心 Visitor 的情况下添加功能：

```csharp
// 实际使用：多层装饰
ITokenWriter original = new TextWriterTokenWriter(writer);
ITokenWriter withSpaces = new InsertRequiredSpacesDecorator(original);
ITokenWriter withTokens = new InsertMissingTokensDecorator(withSpaces);

var visitor = new CSharpOutputVisitor(withTokens, formattingOptions);
syntaxTree.AcceptVisitor(visitor);
```

### 4.4 CSharpAmbience — 简短描述

```csharp
public class CSharpAmbience
{
    // 将类型/成员转为简短描述字符串
    public string ConvertEntity(IEntity entity);
    public string ConvertType(IType type);
    public string ConvertVariable(IVariable variable);

    // 示例: ConvertType("System.Collections.Generic.List<string>")
    //        → "List<string>"
}
```

---

## 五、模式匹配框架

ILSpy 在 C# AST 中使用模式匹配进行声明检测：

```csharp
// CSharp/Syntax/PatternMatching/Pattern.cs
public sealed class Pattern
{
    public INode Root;

    // 在 AST 中查找匹配的子树
    public Match? Match(AstNode node);

    // 常用模式构建
    public static Pattern Create(INode root);
}

// 使用示例：检测 "if (a is T x)" 模式
// var pattern = new Choice {
//     new IfElseStatement {
//         Condition = new IsExpression {
//             Expression = new IdentifierExpression(),
//             Type = new AnyNode("type"),
//             VariableName = new NamedNode("varName")
//         }
//     }.ToStatement()
// }.ToPattern();
```

---

## 六、CSharpResolver — 语义解析

反编译过程不仅需要语法正确，还需要语义正确。`CSharpResolver` 提供 C# 语义分析：

```csharp
public sealed class CSharpResolver
{
    // 类型推断
    public IType? ResolveType(AstType type);

    // 名称解析（标识符 → 类型/成员/变量）
    public ResolveResult ResolveIdentifier(string identifier, ...);
    public ResolveResult ResolveSimpleName(string identifier, ...);

    // 重载决议
    public CSharpInvocationResolveResult ResolveOverload(
        IType[] argumentTypes, ...);

    // 类型转换
    public Conversion WithConversion(Expression expression, IType targetType);

    // 成员查找
    public MemberLookup CreateMemberLookup();
}
```

---

## 实战参考

- [CSharp/Syntax/AstNode.cs](../ICSharpCode.Decompiler/CSharp/Syntax/AstNode.cs) — AST 节点基类
- [CSharp/StatementBuilder.cs](../ICSharpCode.Decompiler/CSharp/StatementBuilder.cs) — StatementBuilder
- [CSharp/ExpressionBuilder.cs](../ICSharpCode.Decompiler/CSharp/ExpressionBuilder.cs) — ExpressionBuilder
- [CSharp/OutputVisitor/CSharpOutputVisitor.cs](../ICSharpCode.Decompiler/CSharp/OutputVisitor/CSharpOutputVisitor.cs) — 输出 Visitor
- [CSharp/Resolver/CSharpResolver.cs](../ICSharpCode.Decompiler/CSharp/Resolver/CSharpResolver.cs) — 语义解析
- [CSharp/Transforms/](../ICSharpCode.Decompiler/CSharp/Transforms/) — AST Transforms