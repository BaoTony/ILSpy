# -*- coding: utf-8 -*-
"""ILSpy API & key entity counter (tree-sitter C# parser, syntax-level accuracy)

Extracts counts that matter for learning docs:
  IL instruction types, IL transforms (by category),
  C# AST node classes (by category: Statement/Expression/TypeMember/Pattern),
  AST transforms, CSharpResolver modules, TypeSystem interfaces,
  Analyzers, FileLoaders, MEF-exported commands.

Usage:
  py -3.13 learning/scripts/ilspy-api.py
"""
import os
import re
import sys
import tree_sitter_c_sharp
from tree_sitter import Language, Parser
from collections import OrderedDict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CS_LANG = Language(tree_sitter_c_sharp.language())
CS_PARSER = Parser(CS_LANG)

TYPE_NODES = {
    'class_declaration', 'struct_declaration', 'interface_declaration',
    'record_declaration', 'record_struct_declaration', 'enum_declaration',
    'delegate_declaration',
}

# Namespace wrappers: traditional `namespace X { }` and file-scoped `namespace X;`
NS_WRAPPERS = {'namespace_declaration', 'file_scoped_namespace_declaration'}


def cs_files(rel_dir, recursive=True):
    """Yield all hand-written .cs files under rel_dir, excluding bin/obj/generated."""
    root = os.path.join(REPO, rel_dir)
    if not os.path.isdir(root):
        return
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ('bin', 'obj')]
            for fn in filenames:
                if fn.endswith('.Designer.cs') or fn.endswith('.g.cs'):
                    continue
                if fn.endswith('.cs'):
                    yield os.path.join(dirpath, fn)
    else:
        for fn in sorted(os.listdir(root)):
            if fn.endswith('.Designer.cs') or fn.endswith('.g.cs'):
                continue
            if fn.endswith('.cs'):
                yield os.path.join(root, fn)


def parse_file(path):
    with open(path, 'rb') as fp:
        src = fp.read()
    return src, CS_PARSER.parse(src)


def node_text(src, node):
    return src[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


def modifiers_of(node):
    return [c.text.decode('utf-8', errors='replace')
            for c in node.children if c.type == 'modifier']


def is_static(node):
    return 'static' in modifiers_of(node)


def get_child(node, *types):
    """tree-sitter 0.24+: child_by_field_name is unreliable.
    Instead, walk named_children and return the first match by type."""
    for c in node.named_children:
        if c.type in types:
            return c
    return None


def top_level_types(src, tree):
    """Yield all top-level type declarations, handling both namespace styles.

    tree-sitter-c-sharp wraps namespace bodies in a `declaration_list` node:
      namespace X.Y { [declaration_list [class Foo {}] [class Bar {}]] }
    So we must descend into declaration_list to reach the actual type nodes.
    """
    root = tree.root_node
    if root.type != 'compilation_unit':
        return
    for cu_child in root.named_children:
        if cu_child.type in NS_WRAPPERS:
            for ns_child in cu_child.named_children:
                if ns_child.type == 'declaration_list':
                    yield from ns_child.named_children
                elif ns_child.type in TYPE_NODES:
                    yield ns_child
        elif cu_child.type in TYPE_NODES:
            yield cu_child


def extract_types(rel_dir, base_filter=None, name_excludes=None):
    """Extract class/struct/enum/interface names from a directory (recursive).

    base_filter: regex on base list (e.g. 'ILInstruction' to find its subclasses)
    name_excludes: list of name patterns (exact match) to exclude
    """
    return _extract_types_impl(rel_dir, base_filter, name_excludes, recursive=True)


def extract_types_flat(rel_dir, base_filter=None, name_excludes=None):
    """Same as extract_types but non-recursive (only direct files in the directory)."""
    return _extract_types_impl(rel_dir, base_filter, name_excludes, recursive=False)


def _extract_types_impl(rel_dir, base_filter, name_excludes, recursive):
    result = OrderedDict()
    for fpath in cs_files(rel_dir, recursive=recursive):
        src, tree = parse_file(fpath)
        for node in top_level_types(src, tree):
            if node.type not in TYPE_NODES:
                continue
            name_node = get_child(node, 'identifier')
            if not name_node:
                continue
            name = node_text(src, name_node)
            if name_excludes:
                skip = False
                for pat in name_excludes:
                    if name == pat:
                        skip = True
                        break
                if skip:
                    continue
            if base_filter:
                base_node = get_child(node, 'base_list')
                if not base_node:
                    continue
                base_text = node_text(src, base_node)
                if not re.search(base_filter, base_text):
                    continue
            result[name] = True
    return result


def extract_class_names(rel_dir, name_excludes=None):
    """Extract all non-static class/struct/record names from a directory."""
    result = OrderedDict()
    for fpath in cs_files(rel_dir):
        src, tree = parse_file(fpath)
        for node in top_level_types(src, tree):
            if node.type not in ('class_declaration', 'struct_declaration', 'record_declaration'):
                continue
            if is_static(node):
                continue
            name_node = get_child(node, 'identifier')
            if not name_node:
                continue
            name = node_text(src, name_node)
            if name_excludes:
                skip = False
                for pat in name_excludes:
                    if name == pat:
                        skip = True
                        break
                if skip:
                    continue
            result[name] = True
    return result


def extract_interfaces(rel_dir):
    """Extract all public interface names and their base interfaces."""
    result = OrderedDict()
    for fpath in cs_files(rel_dir):
        src, tree = parse_file(fpath)
        for node in top_level_types(src, tree):
            if node.type != 'interface_declaration':
                continue
            name_node = get_child(node, 'identifier')
            if not name_node:
                continue
            name = node_text(src, name_node)
            tp_node = get_child(node, 'type_parameters')
            tp_text = ''
            if tp_node:
                tp_text = node_text(src, tp_node)
            base_node = get_child(node, 'base_list')
            base_text = ''
            if base_node:
                base_text = node_text(src, base_node)
            result[name + tp_text] = base_text
    return result


def count_loc(rel_dir):
    """Count lines of code for all .cs files in a directory."""
    total = 0
    by_file = OrderedDict()
    for fpath in sorted(cs_files(rel_dir)):
        with open(fpath, 'rb') as fp:
            lines = sum(1 for _ in fp)
        by_file[os.path.basename(fpath)] = lines
        total += lines
    return total, by_file


def find_attributes(rel_dir, attr_pattern):
    """Count attribute occurrences matching a pattern across all .cs files."""
    count = 0
    for fpath in cs_files(rel_dir):
        src, tree = parse_file(fpath)
        for node in top_level_types(src, tree):
            for attr_list in node.children:
                if attr_list.type == 'attribute_list':
                    attr_text = node_text(src, attr_list)
                    if re.search(attr_pattern, attr_text):
                        count += 1
        # Also check nested types
        for node in tree.root_node.named_children:
            for child in _all_descendants(node):
                if child.type in TYPE_NODES:
                    for attr_list in child.children:
                        if attr_list.type == 'attribute_list':
                            attr_text = node_text(src, attr_list)
                            if re.search(attr_pattern, attr_text):
                                count += 1
    return count


def _all_descendants(node):
    for child in node.named_children:
        yield child
        yield from _all_descendants(child)


def sep(title):
    print()
    print(f"--- {title} ---")


# ============================================================
# 1. IL Layer
# ============================================================
print("=" * 70)
print("ILSpy API & Key Entity Counter  (tree-sitter C# parser)")
print("=" * 70)

sep("IL Instruction Types")
# Only scan the Instructions/ directory (non-recursive), filter by base class containing "Instruction".
# Exclude abstract base classes and utilities.
il_instr = extract_types_flat(
    r"ICSharpCode.Decompiler\IL\Instructions",
    base_filter=r'Instruction',
    name_excludes=[
        'ILInstruction', 'ILFunction', 'BinaryInstruction',
        'SimpleInstruction', 'TryInstruction', 'CompoundAssignmentInstruction',
        'CallInstruction', 'UnaryInstruction', 'MatchInstruction',
        'Nop', 'LockInstruction', 'NullCoalescingInstruction', 'TryCatchHandler',
        'TryFinally', 'TryFault', 'SwitchSection',
        'Block', 'BlockContainer',
    ]
)
# Also check top-level IL/ for instruction containers
il_top = extract_types_flat(
    r"ICSharpCode.Decompiler\IL",
    base_filter=r'ILInstruction',
    name_excludes=['ILInstruction', 'SimpleInstruction', 'Block', 'BlockContainer']
)
all_il = OrderedDict()
all_il.update(il_instr)
all_il.update(il_top)
print(f"  IL instruction/container types: {len(all_il)}")
for name in all_il:
    print(f"    {name}")

sep("IL Transforms")
il_xforms = extract_class_names(
    r"ICSharpCode.Decompiler\IL\Transforms",
    name_excludes=['IILTransform', 'BlockILTransform', 'TransformContext', 'ILTransform']
)
print(f"  IL transforms: {len(il_xforms)}")
for name in il_xforms:
    print(f"    {name}")

sep("IL ControlFlow Transforms")
cf_xforms = extract_class_names(
    r"ICSharpCode.Decompiler\IL\ControlFlow",
    name_excludes=['Graph', 'Point', 'Analysis', 'Context']
)
print(f"  ControlFlow transforms: {len(cf_xforms)}")
for name in cf_xforms:
    print(f"    {name}")
print(f"  [Total IL transforms: {len(il_xforms) + len(cf_xforms)}]")

# ============================================================
# 2. C# AST Nodes
# ============================================================
sep("C# Statement Nodes")
stmts = extract_class_names(
    r"ICSharpCode.Decompiler\CSharp\Syntax\Statements",
    name_excludes=['Statement']
)
print(f"  Statement node types: {len(stmts)}")
for name in stmts:
    print(f"    {name}")

sep("C# Expression Nodes")
exprs = extract_class_names(
    r"ICSharpCode.Decompiler\CSharp\Syntax\Expressions",
    name_excludes=['Expression']
)
print(f"  Expression node types: {len(exprs)}")
for name in exprs:
    print(f"    {name}")

sep("C# TypeMember Nodes")
members = extract_class_names(
    r"ICSharpCode.Decompiler\CSharp\Syntax\TypeMembers",
    name_excludes=['EntityDeclaration']
)
print(f"  TypeMember node types: {len(members)}")
for name in members:
    print(f"    {name}")

gen_scope = extract_class_names(
    r"ICSharpCode.Decompiler\CSharp\Syntax\GeneralScope",
    name_excludes=['AstNode']
)
patterns = extract_class_names(
    r"ICSharpCode.Decompiler\CSharp\Syntax\PatternMatching",
)
ast_total = len(stmts) + len(exprs) + len(members) + len(gen_scope) + len(patterns)
print(f"\n  GeneralScope misc: {len(gen_scope)}")
for name in gen_scope:
    print(f"    {name}")
print(f"  PatternMatching: {len(patterns)}")
for name in patterns:
    print(f"    {name}")

# Top-level Syntax/ types
top_syntax = extract_class_names(
    r"ICSharpCode.Decompiler\CSharp\Syntax",
    name_excludes=['SyntaxTree', 'TextLocation', 'Tokens', 'Indent', 'Comment',
                   'PatternPlaceholder', 'DepthFirst', 'IAstVisitor', 'ITreeVisitable',
                   'OutputStream', 'StringWriter', 'TokenWriter',
                   'OperatorPrecedence', 'CSharpModifierToken']
)
ast_like = OrderedDict()
for name in top_syntax:
    if (name in stmts or name in exprs or name in members or
        name in gen_scope or name in patterns):
        continue
    if name in ('ErrorNode', 'ErrorExpression', 'ErrorStatement', 'TokenRole', 'Roles'):
        continue
    ast_like[name] = True
ast_total += len(ast_like)
print(f"\n  Syntax root types: {len(ast_like)}")
for name in ast_like:
    print(f"    {name}")
print(f"\n  [Total AST node types: ~{ast_total}]")

# ============================================================
# 3. AST Transforms
# ============================================================
sep("AST Transforms")
ast_xforms = extract_class_names(
    r"ICSharpCode.Decompiler\CSharp\Transforms",
    name_excludes=['IAstTransform', 'TransformContext', 'ContextTrackingVisitor', 'CustomPatterns']
)
print(f"  AST transforms: {len(ast_xforms)}")
for name in ast_xforms:
    print(f"    {name}")

# ============================================================
# 4. CSharp Resolver
# ============================================================
sep("CSharp Resolver Modules")
total_loc, by_file = count_loc(r"ICSharpCode.Decompiler\CSharp\Resolver")
for fn, loc in by_file.items():
    pct = loc / total_loc * 100 if total_loc > 0 else 0
    print(f"  {fn:<35} {loc:>5} LOC ({pct:4.1f}%)")
print(f"  {'':<35} {'-----':>5}")
print(f"  {'TOTAL':<35} {total_loc:>5} LOC")

# ============================================================
# 5. TypeSystem Interfaces
# ============================================================
sep("TypeSystem Interface Hierarchy")
ifaces = extract_interfaces(r"ICSharpCode.Decompiler\TypeSystem")
generic_count = 0
for sig, base_txt in ifaces.items():
    if '<' in sig:
        generic_count += 1
    if base_txt:
        print(f"  {sig} : {base_txt}")
    else:
        print(f"  {sig}")
print(f"  ({len(ifaces)} interfaces, {generic_count} use generics)")

# ============================================================
# 6. ILSpyX Analyzers
# ============================================================
sep("ILSpyX Builtin Analyzers")
analyzers = extract_class_names(
    r"ICSharpCode.ILSpyX\Analyzers\Builtin",
    name_excludes=['AnalyzerHelpers']
)
print(f"  Builtin analyzers: {len(analyzers)}")
for name in analyzers:
    print(f"    {name}")

# ============================================================
# 7. File Loaders
# ============================================================
sep("File Loaders")
loaders = extract_class_names(
    r"ICSharpCode.ILSpyX\FileLoaders",
    name_excludes=['FileLoaderRegistry', 'Info', 'Dialog']
)
print(f"  File loaders: {len(loaders)}")
for name in loaders:
    print(f"    {name}")

# ============================================================
# 8. MEF Commands
# ============================================================
sep("MEF-Exported Commands")
export_count = find_attributes(r"ILSpy", r'Export')
print(f"  [Export*] attributes in ILSpy/: {export_count}")

cmd_names = []
for fpath in cs_files(r"ILSpy\Commands"):
    fn = os.path.basename(fpath)
    if fn.endswith('.cs'):
        cmd_names.append(fn.replace('.cs', ''))
cmd_names.sort()
print(f"\n  Command files ({len(cmd_names)}):")
for name in cmd_names:
    print(f"    {name}")

# ============================================================
# 9. CSharp Language Versions
# ============================================================
sep("CSharp Language Versions")
lang_ver_path = os.path.join(REPO, r"ICSharpCode.Decompiler\CSharp\CSharpLanguageVersion.cs")
if os.path.isfile(lang_ver_path):
    with open(lang_ver_path, 'rb') as fp:
        lsrc = fp.read()
    tree = CS_PARSER.parse(lsrc)
    count = 0
    for node in top_level_types(lsrc, tree):
        if node.type == 'enum_declaration':
            for enum_child in node.named_children:
                if enum_child.type == 'enum_member_declaration_list':
                    for enum_member in enum_child.named_children:
                        if enum_member.type == 'enum_member_declaration':
                            name_n = get_child(enum_member, 'identifier')
                            if name_n:
                                name = node_text(lsrc, name_n)
                                if 'CSharp' in name:
                                    count += 1
                                    print(f"    {name}")
    print(f"  Total C# versions: {count}")

# ============================================================
# 10. Disassembler Visitors
# ============================================================
sep("Disassembler Output Visitors")
disasm = extract_class_names(
    r"ICSharpCode.Decompiler\Disassembler",
    name_excludes=['OutputWriter', 'DisassemblerHelpers', 'ReflectionDisassembler']
)
print(f"  Disassembler visitors: {len(disasm)}")
for name in disasm:
    print(f"    {name}")

# ============================================================
# 11. BAML Decompiler
# ============================================================
sep("BAML Decompiler Components")
baml = extract_class_names(
    r"ICSharpCode.BamlDecompiler",
    name_excludes=['DisassemblerHelpers', 'BamlResourceNode']
)
print(f"  BAML components: {len(baml)}")
for name in baml:
    print(f"    {name}")

# ============================================================
# Summary
# ============================================================
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  IL instruction types    : {len(all_il):>4}")
print(f"  IL transforms           : {len(il_xforms):>4} (+ {len(cf_xforms)} ControlFlow = {len(il_xforms) + len(cf_xforms)})")
print(f"  C# Statement nodes      : {len(stmts):>4}")
print(f"  C# Expression nodes     : {len(exprs):>4}")
print(f"  C# TypeMember nodes     : {len(members):>4}")
print(f"  C# AST nodes total      : {ast_total:>4}")
print(f"  AST transforms          : {len(ast_xforms):>4}")
print(f"  Resolver modules        : {len(by_file):>4} ({total_loc:,} LOC total)")
print(f"  TypeSystem interfaces   : {len(ifaces):>4}")
print(f"  Builtin analyzers       : {len(analyzers):>4}")
print(f"  File loaders            : {len(loaders):>4}")
print(f"  BAML components         : {len(baml):>4}")
print(f"  MEF exported commands   : {export_count:>4}")