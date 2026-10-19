# ILSpy 学习笔记

> 文档中的关键数字（项目数、Transform 数、接口数等）以源码为准，变更时需同步更新。

## 目录约定

全部文档按**实际阅读顺序**编号（00-11），文件名即阅读顺序：

```
learning/
├── README.md                    ← 本文件（入口索引）
├── 00-getting-started.md        ← 从这开始：架构速览 + 5 分钟上手 + 搭建环境
├── 01-project-structure.md      ← 源码地图：解决方案全景 + 目录速查
├── 02-metadata-type-system.md   ← 元数据加载 + 类型系统抽象层
├── 03-il-reader-ast.md          ┐
├── 04-il-transforms.md          │ IL 中间表示层：
├── 05-csharp-syntax-tree.md     │ IL 字节码 → ILAst → IL Transform → C# AST
├── 06-csharp-output.md          │ → OutputVisitor 文本输出
├── 07-flow-analysis.md          │ 数据流分析（支配树/定值/到达定义）
├── 08-decompiler-pipeline.md    ┘ 反编译全流程调度
├── 09-frontend-avalonia.md      ┐ 前端交互层（GUI + CLI）
├── 10-cli-tools.md              ┘
├── 11-usage-caveats.md          ← 全程伴随：陷阱与注意事项
├── scripts/                     ← 自动化脚本（Python + PowerShell）
└── archive/                     ← 历史材料
```

## 阅读路径

**新手路径**（从零到理解全库）：按文件名编号 00 → 11 依次阅读。建议节奏：
第 1 天读 00-01（入门 + 源码地图），第 2 天读 02-04（类型系统 → IL 层），
第 3 天读 05-07（C# AST → 输出 → 数据流分析），第 4 天读 08-10（完整管道 → 前端 → CLI），11 号陷阱文档全程伴随。

**按需查阅**：带着问题直接跳文档，见下方矩阵的"真相源"列。

## 文档职责与单一真相源矩阵

| 主题 | 真相源 | 其他文档 |
|---|---|---|
| 新手入门 / 架构速成 / 搭建环境 | `00-getting-started.md` | — |
| 目录树、解决方案、导航速查 | `01-project-structure.md` | — |
| 元数据加载、PEFile、TypeSystem 接口层次 | `02-metadata-type-system.md` | 其余文档仅引用 |
| IL 字节码读取、ILAst 指令体系、控制流 | `03-il-reader-ast.md` | — |
| IL Transform 管道（60+ 步）、内联/循环/async | `04-il-transforms.md` | — |
| C# AST 节点体系（Expression/Statement/TypeMember） | `05-csharp-syntax-tree.md` | — |
| StatementBuilder、ExpressionBuilder、AST Transform、OutputVisitor | `06-csharp-output.md` | — |
| 数据流分析框架（支配树、定值分析、到达定义） | `07-flow-analysis.md` | — |
| 反编译全流程：CSharpDecompiler 调度、DecompileRun、错误恢复、Debug Steps、WholeProjectDecompiler | `08-decompiler-pipeline.md` | — |
| Avalonia UI、MEF 组合、面板系统、分析器 | `09-frontend-avalonia.md` | — |
| ilspycmd CLI、PowerShell、Docker 容器 | `10-cli-tools.md` | — |
| 陷阱（常见错误、配置问题、平台差异） | `11-usage-caveats.md` | 00 号文档仅留速览表 |

## 维护规则

1. **新增内容先查矩阵**：如果主题已有真相源，写进真相源文档，其他地方用链接。
2. **编号即阅读顺序**：新增文档按其在学习路径中的实际位置插入编号；若插入位置在
   中间，需整体重排编号并 grep 同步所有交叉引用（引用格式统一为 `learning/NN-*.md`）。
3. **数字口径以源码为准**：引用数量前先核对目录/枚举实际值。
4. **每篇文档开头的一行职责声明**不得删除，它标注了该文档与矩阵的对应关系。
5. 若某个层未来需要多篇子笔记，可为该层单独建文件夹，届时同步更新本 README 与矩阵。
6. 每篇文档末尾的 `## 实战参考` 节链接到相关测试或源码文件。