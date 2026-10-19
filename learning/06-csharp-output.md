# ILSpy C# 输出生成

> 职责：C# 语法树层后半 — StatementBuilder/ExpressionBuilder · AST Transform（24 步）· OutputVisitor 文本输出 · TypeSystemAstBuilder

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
AST Transforms (24 步)
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

## 一、StatementBuilder — ILAst → C# Statement

### 1.1 ILVisitor 模式

`StatementBuilder` 使用访问者模式将每种 IL 指令映射为 C# 语句：

```csharp
internal sealed class StatementBuilder : ILVisitor<TranslatedStatement>
{
    internal readonly ExpressionBuilder exprBuilder;

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

    // StLoc → VariableDeclarationStatement 或赋值表达式
    protected internal override TranslatedStatement VisitStLoc(StLoc inst)
    {
        var value = exprBuilder.Translate(inst.Value);
        if (ShouldDeclareWhileAssignment(inst.Variable))
            return DeclareVariable(inst.Variable, value);
        else
            return AssignVariable(inst.Variable, value);
    }
}
```

### 1.2 ExpressionBuilder — IL 指令 → C# Expression

```csharp
internal sealed class ExpressionBuilder
{
    public Expression Translate(ILInstruction inst)
    {
        // 递归将 IL 指令转为 C# Expression
        switch (inst)
        {
            case CallInstruction call:
                return TranslateCall(call);
            case Comp comp:
                return TranslateComparison(comp);
            case LdLoc ldloc:
                return new IdentifierExpression(ldloc.Variable.Name);
            case Conv conv:
                return new CastExpression(...);
            // ... 40+ 种指令映射
        }
    }
}
```

### 1.3 方法调用翻译

最重要的翻译逻辑之一：区分方法调用、运算符和属性访问：

```csharp
Expression TranslateCall(CallInstruction call)
{
    var method = call.Method;

    // 运算符检测：op_Addition → a + b
    if (method.IsOperator && TryTranslateOperator(call, out var opExpr))
        return opExpr;

    // 属性访问检测：get_X / set_X → X
    if (IsPropertyAccessor(method, out var prop))
        return TranslatePropertyAccess(prop);

    // 事件访问检测：add_X / remove_X → X += handler
    if (IsEventAccessor(method, out var ev))
        return TranslateEventAccess(ev);

    // 默认：方法调用
    return new InvocationExpression(
        MakeMethodReference(method),
        call.Arguments.Select(Translate).ToList());
}
```

---

## 二、AST Transform 管道（24 步）

### 2.1 变换序列

```csharp
// CSharpDecompiler.GetAstTransforms() — 完整序列
PatternStatementTransform              // 模式语句 → switch/if
RewriteVisualBasicWithEvents           // VB WithEvents
ReplaceMethodCallsWithOperators        // 方法调用 → 运算符
IntroduceUnsafeModifier                // unsafe 修饰符
AddCheckedBlocks                       // checked { } 块
DeclareVariables                       // ★ 声明变量
TransformFieldAndConstructorInitializers // 字段/构造器初始化
FixNameCollisions                      // 解决命名冲突
InsertAnonymousMethodSignatures        // 匿名方法签名
InsertYieldReturnMarkers               // yield return 标记
DecompileForeachStatements             // foreach 语句
NamespaceInsertionTransform            // 命名空间插入
AddXmlDocumentationTransform           // XML 文档注释
FlattenSwitchSections                  // 扁平化 switch 分支
RemoveCompilerAttribute                // 移除编译器生成 Attribute
ReduceIfNesting                        // 减少 if 嵌套
IntroduceUsingDeclarations             // using 声明
IntroduceQueryExpressions              // LINQ 查询表达式
CombineQueryExpressions                // 合并查询表达式
RewriteAssignmentsWithPostIncrement    // 后置自增赋值
HandleStringSwitch                     // string switch
AddAttributes                          // 添加 Attribute
EnableRecordSupport                    // record 支持
EnablePatternMatchingSupport           // 模式匹配支持
```

> 实际 24 步，以 `CSharpDecompiler.cs` 中 `GetAstTransforms()` 为准。

### 2.2 核心 Transform 详解

**DeclareVariables** — 将变量初始化合并到声明：

```csharp
// 变换前：                       // 变换后：
// int x;                         // int x = 5;
// x = 5;
```

**FixNameCollisions** — 处理局部变量与类型/参数命名冲突：

```csharp
// 冲突示例：局部变量名为 typeName，与类型同名
// 变换后：重命名为 typeName1 或使用 @typeName
```

**ReduceIfNesting** — 减少嵌套层级：

```csharp
// 变换前：                       // 变换后：
// if (cond) {                    // if (!cond) return;
//     // 大量代码                // // 大量代码（减少一层缩进）
// }
```

---

## 三、OutputVisitor — C# AST → 文本

### 3.1 访问者模式输出

```csharp
// CSharp/OutputVisitor/CSharpOutputVisitor.cs
public class CSharpOutputVisitor : IAstVisitor
{
    readonly ITokenWriter tokenWriter;
    readonly CSharpFormattingOptions formattingOptions;

    public void VisitMethodDeclaration(MethodDeclaration method)
    {
        // 输出修饰符 (public/static/virtual/...)
        WriteModifiers(method);
        // 输出返回类型
        method.ReturnType.AcceptVisitor(this);
        // 输出方法名
        tokenWriter.WriteIdentifier(method.Name);
        // 输出参数列表
        WriteParameters(method.Parameters);
        // 输出泛型约束
        WriteConstraints(method.Constraints);
        // 输出方法体或分号
        if (method.Body.IsNull)
            tokenWriter.WriteToken(';');
        else
            method.Body.AcceptVisitor(this);
    }

    public void VisitBinaryOperatorExpression(BinaryOperatorExpression expr)
    {
        expr.Left.AcceptVisitor(this);
        tokenWriter.Space();
        tokenWriter.WriteToken(expr.Operator);
        tokenWriter.Space();
        expr.Right.AcceptVisitor(this);
    }

    // ... 覆盖所有 AST 节点类型
}
```

### 3.2 装饰器链 — 自动补全

输出前套上三层装饰器：

```
CSharpOutputVisitor
    → InsertMissingTokensDecorator   ★ 自动补全分号、大括号、逗号
        → InsertRequiredSpacesDecorator  ★ 自动插入必需空格
            → InsertParenthesesVisitor    ★ 自动插入括号（运算符优先级）
                → TextWriterTokenWriter   → StringWriter → string
```

装饰器链确保即使 AST 构建时有遗漏，最终输出仍然是合法 C# 代码。

### 3.3 CSharpFormattingOptions

控制输出风格：

```csharp
public class CSharpFormattingOptions
{
    public static readonly CSharpFormattingOptions Default;
    public int IndentationSize { get; set; } = 4;
    public bool IndentBlocks { get; set; } = true;
    public bool UseTabs { get; set; } = false;
    // ...
}
```

---

## 四、TypeSystemAstBuilder — 类型系统到 AST

将类型系统实体转换为 C# 语法树节点，在输出阶段被广泛使用：

```csharp
// CSharp/Syntax/TypeSystemAstBuilder.cs
public class TypeSystemAstBuilder
{
    public AstType ConvertType(IType type);           // IType → AstType
    public TypeDeclaration ConvertTypeDefinition(ITypeDefinition typeDef);
    public MethodDeclaration ConvertMethod(IMethod method);
    public PropertyDeclaration ConvertProperty(IProperty property);
    public FieldDeclaration ConvertField(IField field);

    public bool UseNullableSpecifier { get; set; }    // 输出 ?
    public bool ShowAttributes { get; set; }           // 输出 Attribute
}
```

---

## 实战参考

- [CSharp/StatementBuilder.cs](../ICSharpCode.Decompiler/CSharp/StatementBuilder.cs) — ILAst → C# Statement
- [CSharp/ExpressionBuilder.cs](../ICSharpCode.Decompiler/CSharp/ExpressionBuilder.cs) — IL 指令 → C# Expression
- [CSharp/CallBuilder.cs](../ICSharpCode.Decompiler/CSharp/CallBuilder.cs) — 方法调用构建
- [CSharp/Transforms/IAstTransform.cs](../ICSharpCode.Decompiler/CSharp/Transforms/IAstTransform.cs) — AST Transform 接口
- [CSharp/OutputVisitor/CSharpOutputVisitor.cs](../ICSharpCode.Decompiler/CSharp/OutputVisitor/CSharpOutputVisitor.cs) — 输出访问者
- [CSharp/Syntax/TypeSystemAstBuilder.cs](../ICSharpCode.Decompiler/CSharp/Syntax/TypeSystemAstBuilder.cs) — TypeSystem → AST