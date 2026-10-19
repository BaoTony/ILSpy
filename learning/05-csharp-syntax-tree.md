# ILSpy C# 语法树节点体系

> 职责：C# 语法树层前半 — AstNode 基类 · Expression（~45 种）· Statement（~30 种）· TypeMember · PatternMatching

---

## 数据流视角

```
结构化 ILAst (IL Transform 管道输出)
    ↓
StatementBuilder.Convert(ILInstruction)  → C# Statement      → 详见 06-csharp-output
ExpressionBuilder.Translate(...)         → C# Expression
    ↓
C# SyntaxTree (本章详析)
    └── NamespaceDeclaration
          └── TypeDeclaration (class/struct/interface/enum/delegate)
                ├── MethodDeclaration → BlockStatement → ...
                ├── PropertyDeclaration
                ├── FieldDeclaration
                └── ...
```

---

## 一、C# AST 树结构概览

```
SyntaxTree (根节点)
├── UsingDeclaration[]          using 语句
├── ExternAliasDeclaration[]    extern 别名
├── AttributeSection[]          程序集级 Attribute
├── NamespaceDeclaration        命名空间
│     └── TypeDeclaration       class/struct/interface/enum/delegate
│           ├── AttributeSection[]
│           ├── Constraint[]    泛型约束 (where T : ...)
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

---

## 二、AstNode — 核心基类

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

    // 注释系统
    public void AddAnnotation<T>(T annotation);
    public T? Annotation<T>();
}
```

关键派生路径：

```
AstNode
├── EntityDeclaration
│     ├── TypeDeclaration
│     │     ├── MethodDeclaration
│     │     ├── PropertyDeclaration
│     │     ├── FieldDeclaration
│     │     └── ...
│     ├── NamespaceDeclaration
│     └── ParameterDeclaration
├── Statement
│     ├── BlockStatement
│     ├── IfElseStatement
│     └── ...
└── Expression
      ├── InvocationExpression
      ├── BinaryOperatorExpression
      └── ...
```

---

## 三、Expression（表达式）分类

（约 45 种表达式节点，完整覆盖 C# 所有表达式语法）

```
Expression (抽象基类)
├── 基本表达式
│   ├── PrimitiveExpression      字面量 (42, "hello", 3.14, true)
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
│   ├── ArrayCreateExpression    new T[] { ... }
│   └── AnonymousMethodExpression 匿名方法 / Lambda
│
├── 运算符
│   ├── BinaryOperatorExpression a + b, a && b, a ?? b, ...
│   ├── UnaryOperatorExpression  -a, !a, ~a, ++a, ...
│   ├── AssignmentExpression     a = b, a += b, ...
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
│   ├── WithInitializerExpression  r with { A = 1 }
│   ├── AnonymousTypeCreateExpression  new { A = 1 }
│   └── StackAllocExpression     stackalloc T[n]
│
├── 指针 / unsafe
│   ├── DirectionExpression      ref x
│   ├── AddressOfExpression      &x
│   ├── PointerDereferenceExpression  *p
│   └── CheckedExpression        checked(expr)
│
└── 模式匹配 (PatternMatching 子命名空间)
    ├── Match                    is 模式匹配
    ├── Choice                   or 模式
    ├── Repeat                   数组/列表模式
    └── ...
```

---

## 四、Statement（语句）分类

（约 30 种语句节点）

```
Statement (抽象基类)
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
│   ├── GotoCaseStatement         goto case 1;
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

## 五、TypeMembers — 类型成员节点

```
EntityDeclaration → TypeDeclaration → Members:
├── MethodDeclaration         方法声明
│     ├── ParameterDeclaration[]  参数
│     ├── TypeParameterDeclaration[] 泛型参数
│     ├── AttributeSection[]      方法级 Attribute
│     └── BlockStatement          方法体
│
├── PropertyDeclaration        属性声明
│     ├── Accessor (get/set/init)  访问器
│     └── Expression              初始值
│
├── FieldDeclaration           字段声明
├── EventDeclaration           事件声明
├── ConstructorDeclaration     构造函数
│     └── ConstructorInitializer  : base(...) / : this(...)
├── OperatorDeclaration        运算符重载
├── IndexerDeclaration         索引器
├── DestructorDeclaration      析构函数 (~)
└── EnumMemberDeclaration      枚举成员
```

---

## 实战参考

- [CSharp/Syntax/AstNode.cs](../ICSharpCode.Decompiler/CSharp/Syntax/AstNode.cs) — 基类
- [CSharp/Syntax/SyntaxTree.cs](../ICSharpCode.Decompiler/CSharp/Syntax/SyntaxTree.cs) — 语法树根
- [CSharp/Syntax/Expressions/](../ICSharpCode.Decompiler/CSharp/Syntax/Expressions/) — 所有表达式节点
- [CSharp/Syntax/Statements/](../ICSharpCode.Decompiler/CSharp/Syntax/Statements/) — 所有语句节点
- [CSharp/Syntax/TypeMembers/](../ICSharpCode.Decompiler/CSharp/Syntax/TypeMembers/) — 类型成员节点
- [CSharp/Syntax/PatternMatching/](../ICSharpCode.Decompiler/CSharp/Syntax/PatternMatching/) — 模式匹配