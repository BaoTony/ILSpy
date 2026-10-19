# ILSpy 学习笔记

> 文档中的关键数字（项目数、Transform 数、接口数等）以源码为准，变更时需同步更新。

## 目录约定

全部文档按**实际阅读顺序**编号（00-08），文件名即阅读顺序：

```
learning/
├── README.md                    ← 本文件（入口索引）
├── 00-getting-started.md        ← 从这开始：架构速览 + 5 分钟上手 + 搭建环境
├── 01-project-structure.md      ← 源码地图：解决方案全景 + 目录速查
├── 02-metadata-type-system.md   ← 元数据加载 + 类型系统抽象层
├── 03-il-layer.md               ┐
├── 04-csharp-ast.md             │ 主反编译管道（自底向上：
├── 05-decompiler-pipeline.md    │ IL 字节码 → ILAst → C# AST → 文本输出）
├── 06-frontend-avalonia.md      ┐ 前端交互层（GUI + CLI）
├── 07-cli-tools.md              ┘
├── 08-usage-caveats.md          ← 全程伴随：陷阱与注意事项
└── archive/                     ← 历史材料
```

## 阅读路径

**新手路径**（从零到理解全库）：按文件名编号 00 → 08 依次阅读。建议节奏：
第 1 天读 00-01（入门 + 源码地图），第 2 天读 02-04（类型系统 → IL → C# AST），
第 3 天读 05-07（完整管道 → 前端 UI → CLI），08 号陷阱文档全程伴随、改代码前先过一遍。

**按需查阅**：带着问题直接跳文档，见下方矩阵的"真相源"列。

## 文档职责与单一真相源矩阵

同一主题的内容只以一份文档为准（真相源），其他文档只链接、不复制：

| 主题 | 真相源 | 其他文档 |
|---|---|---|
| 新手入门 / 架构速成 / 搭建环境 | `00-getting-started.md` | — |
| 目录树、解决方案、导航速查 | `01-project-structure.md` | — |
| 元数据加载、PEFile、TypeSystem 接口层次 | `02-metadata-type-system.md` | 其余文档仅引用 |
| IL 字节码读取、ILAst 指令、IL Transform 管道 | `03-il-layer.md` | — |
| C# AST 语法节点、StatementBuilder、AST Transform | `04-csharp-ast.md` | — |
| 完整反编译管道：CSharpDecompiler 调度、DecompileRun、错误恢复、WholeProjectDecompiler 导出引擎 | `05-decompiler-pipeline.md` | — |
| Avalonia UI、MEF 组合、面板系统、分析器 | `06-frontend-avalonia.md` | — |
| ilspycmd CLI、PowerShell、Docker 容器 | `07-cli-tools.md` | — |
| 陷阱（常见错误、配置问题、平台差异） | `08-usage-caveats.md` | 00 号文档仅留速览表 |

## 维护规则

1. **新增内容先查矩阵**：如果主题已有真相源，写进真相源文档，其他地方用链接。
2. **编号即阅读顺序**：新增文档按其在学习路径中的实际位置插入编号；若插入位置在
   中间，需整体重排编号并 grep 同步所有交叉引用（引用格式统一为 `learning/NN-*.md`）。
3. **数字口径以源码为准**：引用数量前先核对目录/枚举实际值。
4. **每篇文档开头的一行职责声明**不得删除，它标注了该文档与矩阵的对应关系。
5. 若某个层未来需要多篇子笔记，可为该层单独建文件夹，届时同步更新本 README 与矩阵。
6. 每篇文档末尾的 `## 实战参考` 节链接到相关测试或源码文件。