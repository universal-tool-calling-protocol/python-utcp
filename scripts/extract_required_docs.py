#!/usr/bin/env python3
"""
Script to extract REQUIRED docstrings from UTCP codebase and generate Docusaurus documentation.

This script scans all Python files in core/ and plugins/ directories, extracts docstrings
that start with "REQUIRED", and generates organized Docusaurus markdown files.
"""

import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class DocEntry:
    """Represents a documentation entry extracted from code."""
    name: str
    type: str  # 'module', 'class', 'function', 'method'
    docstring: str
    file_path: str
    line_number: int
    parent_class: Optional[str] = None
    signature: Optional[str] = None  # Function/method signature
    class_fields: Optional[List[str]] = None  # Non-private class attributes
    base_classes: Optional[List[str]] = None  # Parent classes (excluding Python built-ins)


class RequiredDocExtractor:
    """Extracts REQUIRED docstrings from Python files and generates Docusaurus docs."""
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.doc_entries: List[DocEntry] = []
        self.class_index: Dict[str, str] = {}  # class_name -> file_path mapping
        self.output_file_mapping: Dict[str, str] = {}  # source_file_path -> output_file_path mapping
    
    def is_required_docstring(self, docstring: str) -> bool:
        """Check if docstring starts with REQUIRED."""
        if not docstring:
            return False
        return docstring.strip().startswith("REQUIRED")
    
    def clean_docstring(self, docstring: str) -> str:
        """Clean and format docstring for markdown output."""
        if not docstring:
            return ""
        
        # Remove REQUIRED prefix
        lines = docstring.strip().split('\n')
        if lines[0].strip() == "REQUIRED":
            lines = lines[1:]
        elif lines[0].strip().startswith("REQUIRED"):
            lines[0] = lines[0].replace("REQUIRED", "", 1).strip()
        
        # Remove common indentation
        if lines:
            # Find minimum indentation (excluding empty lines)
            non_empty_lines = [line for line in lines if line.strip()]
            if non_empty_lines:
                min_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)
                lines = [line[min_indent:] if line.strip() else line for line in lines]
        
        return '\n'.join(lines).strip()
    
    def convert_docstring_to_html_markdown(self, docstring: str) -> str:
        """Convert Google-style docstring to HTML markdown for Docusaurus.
        
        Args:
            docstring: The raw docstring text
            
        Returns:
            HTML markdown formatted string suitable for Docusaurus
        """
        if not docstring:
            return "*No documentation available*"
        
        if docstring.startswith("REQUIRED"):
            docstring = docstring.replace("REQUIRED", "", 1).strip()
        if docstring.startswith("\n"):
            docstring = docstring[1:]

        lines = docstring.split('\n')
        result = []
        current_section = None
        current_section_content = []
        
        # Common Google-style section headers
        section_headers = {
            'args:', 'arguments:', 'parameters:', 'param:', 'params:',
            'returns:', 'return:', 'yields:', 'yield:',
            'raises:', 'except:', 'exceptions:',
            'examples:', 'example:',
            'note:', 'notes:',
            'warning:', 'warnings:',
            'see also:', 'seealso:',
            'attributes:', 'attr:', 'attrs:',
            'methods:', 'method:',
            'properties:', 'property:', 'props:'
        }
        
        def process_section_content(content_lines):
            """Process content lines within a section."""
            if not content_lines:
                return []
            
            processed = []
            i = 0
            in_code_block = False
            
            while i < len(content_lines):
                line = content_lines[i]
                stripped = line.strip()
                
                # Check for code block delimiters
                if stripped.startswith('```'):
                    # Check if code block is started and closed on the same line
                    if stripped.count('```') >= 2:
                        processed.append(stripped)
                        i += 1
                        continue
                    else:
                        in_code_block = not in_code_block
                        processed.append(stripped)
                        i += 1
                        continue
                
                # If we're inside a code block, preserve the line as-is
                if in_code_block:
                    processed.append(line.rstrip())
                    i += 1
                    continue
                
                # Skip empty lines
                if not stripped:
                    processed.append('')
                    i += 1
                    continue
                
                # Clean up multiple consecutive empty lines
                while '\n\n\n' in line:
                    line = line.replace('\n\n\n', '\n\n')
                    stripped = line.strip()
                
                # Escape any remaining curly braces for Docusaurus
                line = line.replace('{', '\\{').replace('}', '\\}')
                stripped = line.strip()

                # Check if this looks like a parameter/item definition (name: description)
                if ':' in stripped and not stripped.endswith(':'):
                    colon_pos = stripped.find(':')
                    param_name = stripped[:colon_pos].strip()
                    param_desc = stripped[colon_pos + 1:].strip()
                    
                    # Check if param_name looks like a parameter (no spaces, reasonable length)
                    if ' ' not in param_name and len(param_name) <= 50 and param_name.replace('_', '').isalnum():
                        # This is likely a parameter definition
                        processed.append(f"- **`{param_name}`**: {param_desc}")
                        
                        # Check for continuation lines (indented more than the parameter line)
                        base_indent = len(line) - len(line.lstrip())
                        i += 1
                        while i < len(content_lines):
                            next_line = content_lines[i]
                            next_stripped = next_line.strip()
                            next_indent = len(next_line) - len(next_line.lstrip()) if next_stripped else 0
                            
                            # Check if we hit a code block
                            if next_stripped.startswith('```'):
                                break
                            
                            if not next_stripped:
                                # Empty line - add it and continue
                                processed.append('')
                                i += 1
                            elif next_indent > base_indent:
                                # Continuation line - add with proper spacing
                                processed.append(f"  {next_stripped}")
                                i += 1
                            else:
                                # Not a continuation, back up and break
                                break
                        continue
                
                # Check if line starts with a list marker
                elif stripped.startswith(('- ', '* ', '+ ')):
                    # This is already a markdown list item
                    processed.append(stripped)
                elif stripped.startswith(('1. ', '2. ', '3. ', '4. ', '5. ', '6. ', '7. ', '8. ', '9. ')):
                    # Numbered list item
                    processed.append(stripped)
                else:
                    # Regular paragraph text
                    processed.append(stripped)
                
                i += 1
            
            return processed
        
        if docstring.__contains__('{VAR}'):
            print("")
        # Parse the docstring line by line
        for line in lines:
            stripped_lower = line.strip().lower()
            
            # Check if this line is a section header
            if stripped_lower in section_headers or stripped_lower.endswith(':'):
                # Save previous section if it exists
                if current_section:
                    processed_content = process_section_content(current_section_content)
                    if processed_content:
                        result.append(f"\n**{current_section.title()}**\n")
                        result.extend(processed_content)
                        result.append('')
                else:
                    processed_content = process_section_content(current_section_content)
                    if processed_content:
                        result.extend(processed_content)
                
                # Start new section
                current_section = line.strip().rstrip(':')
                current_section_content = []
            else:
                current_section_content.append(line)
        
        # Process the last section
        if current_section:
            processed_content = process_section_content(current_section_content)
            if processed_content:
                result.append(f"\n**{current_section.title()}**\n")
                result.extend(processed_content)
        
        # Clean up the result
        final_result = []
        for line in result:
            if isinstance(line, str):
                final_result.append(line)
        
        # Join and clean up extra whitespace
        markdown_text = '\n'.join(final_result)
        
        return markdown_text.strip()
    
    def get_function_signature(self, node: ast.FunctionDef) -> str:
        """Extract function signature from AST node."""
        try:
            # Handle both sync and async functions
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            
            # Get function name
            sig_parts = [prefix + node.name + "("]
            
            # Process arguments
            args = []
            
            # Regular arguments
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                args.append(arg_str)
            
            # *args
            if node.args.vararg:
                vararg_str = f"*{node.args.vararg.arg}"
                if node.args.vararg.annotation:
                    vararg_str += f": {ast.unparse(node.args.vararg.annotation)}"
                args.append(vararg_str)
            
            # **kwargs
            if node.args.kwarg:
                kwarg_str = f"**{node.args.kwarg.arg}"
                if node.args.kwarg.annotation:
                    kwarg_str += f": {ast.unparse(node.args.kwarg.annotation)}"
                args.append(kwarg_str)
            
            sig_parts.append(", ".join(args))
            sig_parts.append(")")
            
            # Return type annotation
            if node.returns:
                sig_parts.append(f" -> {ast.unparse(node.returns)}")
            
            return "".join(sig_parts)
        except Exception:
            # Fallback to simple signature
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            return f"{prefix}{node.name}(...)"
    
    def get_class_fields(self, node: ast.ClassDef) -> List[str]:
        """Extract non-private class fields from AST node."""
        fields = []
        
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                # Type annotated attribute
                field_name = item.target.id
                if not field_name.startswith('_'):  # Skip private fields
                    annotation = ast.unparse(item.annotation) if item.annotation else ""
                    fields.append(f"{field_name}: {annotation}")
            elif isinstance(item, ast.Assign):
                # Regular assignment
                for target in item.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith('_'):
                        fields.append(target.id)
        
        return fields
    
    def get_class_base_classes(self, node: ast.ClassDef) -> List[str]:
        """Extract base classes from AST node, excluding Python built-ins."""
        # Common Python built-ins to exclude
        exclude_bases = {
            'ABC', 'BaseModel', 'object', 'Exception', 'BaseException',
            'dict', 'list', 'str', 'int', 'float', 'bool', 'tuple', 'set',
            'Generic', 'Enum', 'IntEnum', 'NamedTuple'
        }
        
        base_classes = []
        for base in node.bases:
            try:
                base_name = ast.unparse(base)
                # Extract just the class name if it's a complex expression
                if '.' in base_name:
                    base_name = base_name.split('.')[-1]
                
                if base_name not in exclude_bases:
                    base_classes.append(base_name)
            except Exception:
                # Skip if we can't parse the base class
                pass
        
        return base_classes

    def extract_from_file(self, file_path: Path) -> List[DocEntry]:
        """Extract REQUIRED docstrings from a single Python file."""
        entries = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse AST
            tree = ast.parse(content, filename=str(file_path))
            
            # Extract module-level docstring
            module_docstring = ast.get_docstring(tree)
            if self.is_required_docstring(module_docstring):
                entries.append(DocEntry(
                    name=file_path.stem,
                    type='module',
                    docstring=self.convert_docstring_to_html_markdown(module_docstring),
                    file_path=str(file_path.relative_to(self.root_path)).replace('\\', '/'),
                    line_number=1
                ))
            
            # Track class methods to avoid duplicating them as functions
            class_methods = set()
            
            # First pass: extract classes and methods
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_docstring = ast.get_docstring(node)
                    if self.is_required_docstring(class_docstring):
                        class_fields = self.get_class_fields(node)
                        base_classes = self.get_class_base_classes(node)
                        entries.append(DocEntry(
                            name=node.name,
                            type='class',
                            docstring=self.convert_docstring_to_html_markdown(class_docstring),
                            file_path=str(file_path.relative_to(self.root_path)).replace('\\', '/'),
                            line_number=node.lineno,
                            class_fields=class_fields,
                            base_classes=base_classes
                        ))
                    
                    # Extract methods from class (both sync and async)
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            class_methods.add(id(item))  # Track this method
                            method_docstring = ast.get_docstring(item)
                            if self.is_required_docstring(method_docstring):
                                signature = self.get_function_signature(item)
                                if signature.__contains__('find_required_variables'):
                                    print("test")
                                entries.append(DocEntry(
                                    name=item.name,
                                    type='method',
                                    docstring=self.convert_docstring_to_html_markdown(method_docstring),
                                    file_path=str(file_path.relative_to(self.root_path)).replace('\\', '/'),
                                    line_number=item.lineno,
                                    parent_class=node.name,
                                    signature=signature
                                ))
            
            # Second pass: extract top-level functions (not already processed as methods)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and id(node) not in class_methods:
                    func_docstring = ast.get_docstring(node)
                    if self.is_required_docstring(func_docstring):
                        signature = self.get_function_signature(node)
                        entries.append(DocEntry(
                            name=node.name,
                            type='function',
                            docstring=self.convert_docstring_to_html_markdown(func_docstring),
                            file_path=str(file_path.relative_to(self.root_path)).replace('\\', '/'),
                            line_number=node.lineno,
                            signature=signature
                        ))
        
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
        
        return entries
    
    def scan_directories(self, directories: List[str]) -> None:
        """Scan specified directories for Python files."""
        for directory in directories:
            dir_path = self.root_path / directory
            if not dir_path.exists():
                print(f"Warning: Directory {dir_path} does not exist")
                continue
            
            for py_file in dir_path.rglob("*.py"):
                entries = self.extract_from_file(py_file)
                self.doc_entries.extend(entries)
                
                # Build class index for cross-references
                for entry in entries:
                    if entry.type == 'class':
                        self.class_index[entry.name] = entry.file_path.replace('\\', '/')
    
    def organize_by_module(self) -> Dict[str, Dict[str, List[DocEntry]]]:
        """Organize documentation entries by module/file."""
        modules = {}
        
        for entry in self.doc_entries:
            file_key = entry.file_path.replace('\\', '/')
            if file_key not in modules:
                modules[file_key] = {
                    'module': [],
                    'classes': [],
                    'functions': [],
                    'methods': []
                }
            
            if entry.type == 'module':
                modules[file_key]['module'].append(entry)
            elif entry.type == 'class':
                modules[file_key]['classes'].append(entry)
            elif entry.type == 'function':
                modules[file_key]['functions'].append(entry)
            elif entry.type == 'method':
                modules[file_key]['methods'].append(entry)
        
        # Sort entries within each file
        for file_data in modules.values():
            for category in file_data.values():
                category.sort(key=lambda x: x.line_number)
        
        return modules
    
    def add_cross_references(self, text: str, current_file_path: str) -> str:
        """Placeholder method for cross-references during first pass generation."""
        # During first pass, we don't have output file paths yet
        # All cross-referencing will be done in post-generation step
        return text
    
    def format_field_with_references(self, field: str, current_file_path: str) -> str:
        """Format a field with proper cross-references and styling."""
        if ':' not in field:
            return f"`{field}`"
        
        field_name, field_type = field.split(':', 1)
        field_name = field_name.strip()
        field_type = field_type.strip()
        
        # Will be replaced with actual links after file generation
        return f"`{field_name}: {field_type}`"
    
    def add_cross_references_post_generation(self, text: str, current_output_file: str) -> str:
        """Add cross-references using actual output file paths."""
        if not text:
            return text
            
        modified_text = text
        for class_name, source_file_path in self.class_index.items():
            pattern = r'\b' + re.escape(class_name) + r'\b'
            if re.search(pattern, modified_text):
                target_output_file = self.output_file_mapping.get(source_file_path)
                if not target_output_file:
                    continue
                    
                if target_output_file == current_output_file:
                    pass
                    # Same file - just anchor
                    # class_anchor = re.sub(r'[^\w\-_]', '-', class_name.lower()).strip('-')
                    # link = f"[{class_name}](#{class_anchor})"
                    link = class_name
                else:
                    # Different file - calculate actual relative path
                    current_dir = Path(current_output_file).parent
                    target_path = Path(target_output_file)
                    
                    try:
                        relative_path = str(target_path.relative_to(current_dir)).replace('\\', '/')
                        class_anchor = re.sub(r'[^\w\-_]', '-', class_name.lower()).strip('-')
                        link = f"[{class_name}](./{relative_path}#{class_anchor})"
                    except ValueError:
                        # Files are in different trees, calculate with .. navigation
                        current_parts = current_dir.parts
                        target_parts = target_path.parent.parts
                        
                        # Find common prefix
                        common_len = 0
                        for i in range(min(len(current_parts), len(target_parts))):
                            if current_parts[i] == target_parts[i]:
                                common_len += 1
                            else:
                                break
                        
                        # Build relative path
                        up_steps = len(current_parts) - common_len
                        down_steps = target_parts[common_len:]
                        
                        path_components = ['..'] * up_steps + list(down_steps) + [target_path.name]
                        relative_path_str = '/'.join(path_components)
                        
                        class_anchor = re.sub(r'[^\w\-_]', '-', class_name.lower()).strip('-')
                        link = f"[{class_name}](./{relative_path_str}#{class_anchor})"
                
                # Don't replace matches that are in code blocks
                lines = modified_text.split('\n')
                in_code_block = False
                for i, line in enumerate(lines):
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                    elif not in_code_block:
                        lines[i] = re.sub(pattern, link, line)
                modified_text = '\n'.join(lines)
        
        return modified_text
    
    def generate_module_markdown(self, file_path: str, file_data: Dict[str, List[DocEntry]]) -> str:
        """Generate markdown content for a single module/file."""
        if not any(file_data.values()):
            return ""
        
        # Clean up file path for display
        display_path = file_path
        if display_path.startswith('core/src/'):
            display_path = display_path[9:]  # Remove 'core/src/' prefix
        elif display_path.startswith('plugins/'):
            display_path = display_path[8:]  # Remove 'plugins/' prefix
        
        # Create title from file name only
        title = Path(display_path).stem
        
        content = [
            "---",
            f"title: {title}",
            f"sidebar_label: {title}",
            "---",
            "",
            f"# {title}",
            "",
            f"**File:** `{file_path}`",
            "",
        ]
        
        # Add module docstring if present
        if file_data['module']:
            module_entry = file_data['module'][0]
            content.extend([
                "## Module Description",
                "",
                module_entry.docstring if module_entry.docstring else "*No module documentation available*",
                "",
            ])
        
        # Group methods by their parent class
        methods_by_class = {}
        for method in file_data['methods']:
            class_name = method.parent_class or 'Unknown'
            if class_name not in methods_by_class:
                methods_by_class[class_name] = []
            methods_by_class[class_name].append(method)
        
        # Add classes with their methods
        if file_data['classes']:
            for class_entry in file_data['classes']:
                # Create anchor-friendly ID
                class_anchor = re.sub(r'[^\w\-_]', '-', class_entry.name.lower()).strip('-')
                
                # Create class header with optional parent classes in parentheses
                class_header = f"### class {class_entry.name}"
                if class_entry.base_classes:
                    base_classes_with_links = []
                    for base_class in class_entry.base_classes:
                        linked_base = self.add_cross_references(base_class, file_path)
                        base_classes_with_links.append(linked_base)
                    class_header += f" ({', '.join(base_classes_with_links)})"
                class_header += f" {{#{class_anchor}}}"
                
                content.extend([
                    class_header,
                    "",
                ])
                
                # Add class docstring
                if class_entry.docstring:
                    content.extend([
                        "<details>",
                        "<summary>Documentation</summary>",
                        "",
                        class_entry.docstring,

                        "</details>",
                        "",
                    ])
                else:
                    content.extend(["*No class documentation available*", ""])
                
                # Add class fields if available
                if class_entry.class_fields:
                    content.extend(["#### Fields:", ""])
                    for field in class_entry.class_fields:
                        formatted_field = self.format_field_with_references(field, file_path)
                        content.append(f"- {formatted_field}")
                    content.append("")
                
                # Add methods for this class
                if class_entry.name in methods_by_class:
                    content.extend(["#### Methods:", ""])
                    
                    for method in methods_by_class[class_entry.name]:
                        method_anchor = re.sub(r'[^\w\-_]', '-', f"{class_entry.name}-{method.name}".lower()).strip('-')
                        
                        # Add cross-references to method signature
                        linked_signature = self.add_cross_references(method.signature, file_path)
                        
                        docstrings = ""
                        
                        if method.docstring:
                            docstrings = method.docstring
                        else:
                            docstrings = "*No method documentation available*"
                            
                        content.extend(
                            [
                                "<details>",
                                f"<summary>{linked_signature}</summary>",
                                "",
                                docstrings,
                                "</details>",
                                "",
                            ]
                        )
                
                content.extend(["---", ""])
        
        # Add standalone functions
        if file_data['functions']:
            for func_entry in file_data['functions']:
                func_anchor = re.sub(r'[^\w\-_]', '-', func_entry.name.lower()).strip('-')
                
                # Add cross-references to function signature
                linked_signature = self.add_cross_references(func_entry.signature, file_path)
                
                content.extend([
                    f"### Function {linked_signature} {{#{func_anchor}}}",
                    "",
                ])
                
                if func_entry.docstring:
                    content.extend([
                        "<details>",
                        "<summary>Documentation</summary>",
                        "",
                        func_entry.docstring,
                        "</details>",
                        "",
                    ])
                else:
                    content.extend(["*No function documentation available*", ""])
                
                content.extend(["---", ""])
        
        return '\n'.join(content)
    
    def generate_index_file(self, modules: Dict[str, Dict[str, List[DocEntry]]], output_path: Path) -> str:
        """Generate the main index file."""
        total_entries = sum(sum(len(entries) for entries in file_data.values()) for file_data in modules.values())
        
        content = [
            "---",
            "title: UTCP API Reference",
            "sidebar_label: API Specification",
            "---",
            "",
            "# UTCP API Reference",
            "",
            "API specification of a UTCP-compliant client implementation. Any implementation of a UTCP Client needs to have all of the classes, functions and fields described in this specification.",
            "",
            "This specification is organized by module of the reference python implementation to provide a comprehensive understanding of UTCP's architecture.",
            "",
            "**Note:** The modules don't have to be implemented in the same way as in the reference implementation, but all of the functionality here needs to be provided.",
            "",
            f"**Total documented items:** {total_entries}",
            f"**Modules documented:** {len(modules)}",
            ""
        ]
        
        # Group modules by category
        core_modules = []
        plugin_modules = []
        
        for file_path in sorted(modules.keys()):
            display_path = file_path
            if display_path.startswith('core/src/'):
                display_path = display_path[9:]
                core_modules.append((file_path, display_path))
            elif display_path.startswith('plugins/'):
                display_path = display_path[8:]
                plugin_modules.append((file_path, display_path))
            else:
                core_modules.append((file_path, display_path))
        
        # Add core modules
        if core_modules:
            content.extend([
                "## Core Modules",
                "",
                "Core UTCP framework components that define the fundamental interfaces and implementations.",
                ""
            ])
            
            for file_path, display_path in core_modules:
                file_data = modules[file_path]
                total_items = sum(len(entries) for entries in file_data.values())
                title = display_path.replace('/', '.').replace('.py', '')
                
                # Get actual output file path and create relative link from index
                output_file_path = self.output_file_mapping.get(file_path)
                if output_file_path:
                    # Calculate relative path from index to the actual output file
                    index_path = output_path / "index.md"
                    target_path = Path(output_file_path)
                    try:
                        relative_path = target_path.relative_to(output_path)
                        link_path = f"./{relative_path}"
                    except ValueError:
                        # Fallback to simple filename if relative path calculation fails
                        link_path = f"./{target_path.name}"
                else:
                    # Fallback to old method if output file path not found
                    file_anchor = title.replace('.', '-').lower()
                    link_path = f"./{file_anchor}"
                
                content.extend([
                    f"### [{title}]({link_path})",
                    ""
                ])
                
                # Add summary of what's in this module
                items = []
                if file_data['classes']:
                    items.append(f"{len(file_data['classes'])} classes")
                if file_data['functions']:
                    items.append(f"{len(file_data['functions'])} functions")
                if file_data['methods']:
                    items.append(f"{len(file_data['methods'])} methods")
                
                if items:
                    content.append(f"- **Contains:** {', '.join(items)}")
                
                # Add module description if available
                if file_data['module']:
                    module_desc = file_data['module'][0].docstring
                    if module_desc:
                        # Get first line of description
                        first_line = module_desc.split('\n')[0].strip()
                        content.append(f"- **Description:** {first_line}")
                
                content.extend(["", ""])
        
        # Add plugin modules
        if plugin_modules:
            content.extend([
                "## Plugin Modules",
                "",
                "Plugin implementations that extend UTCP with specific transport protocols and capabilities.",
                ""
            ])
            
            for file_path, display_path in plugin_modules:
                file_data = modules[file_path]
                title = display_path.replace('/', '.').replace('.py', '')
                
                # Get actual output file path and create relative link from index
                output_file_path = self.output_file_mapping.get(file_path)
                if output_file_path:
                    # Calculate relative path from index to the actual output file
                    index_path = output_path / "index.md"
                    target_path = Path(output_file_path)
                    try:
                        relative_path = target_path.relative_to(output_path)
                        link_path = f"./{relative_path}"
                    except ValueError:
                        # Fallback to simple filename if relative path calculation fails
                        link_path = f"./{target_path.name}"
                else:
                    # Fallback to old method if output file path not found
                    file_anchor = title.replace('.', '-').lower()
                    link_path = f"./{file_anchor}"
                
                content.extend([
                    f"### [{title}]({link_path})",
                    ""
                ])
                
                # Add summary
                items = []
                if file_data['classes']:
                    items.append(f"{len(file_data['classes'])} classes")
                if file_data['functions']:
                    items.append(f"{len(file_data['functions'])} functions")
                if file_data['methods']:
                    items.append(f"{len(file_data['methods'])} methods")
                
                if items:
                    content.append(f"- **Contains:** {', '.join(items)}")
                
                if file_data['module']:
                    module_desc = file_data['module'][0].docstring
                    if module_desc:
                        first_line = module_desc.split('\n')[0].strip()
                        content.append(f"- **Description:** {first_line}")
                
                content.extend(["", ""])
        
        # Add about UTCP section
        content.extend([
            "## About UTCP",
            "",
            "The Universal Tool Calling Protocol (UTCP) is a framework for calling tools across various transport protocols.",
            "This API reference covers all the essential interfaces, implementations, and extension points needed to:",
            "",
            "- **Implement** new transport protocols",
            "- **Extend** UTCP with custom functionality",
            "- **Integrate** UTCP into your applications",
            "- **Understand** the complete UTCP architecture",
        ])
        
        return '\n'.join(content)
    
    def generate_docs(self, output_dir: str) -> None:
        """Generate all documentation files organized in folders."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        modules = self.organize_by_module()
        generated_files = {}  # file_path -> (content, output_file_path)
        
        # First pass: Generate all files without cross-references and track output paths
        for file_path, file_data in modules.items():
            if any(file_data.values()):  # Only generate if there's content
                content = self.generate_module_markdown(file_path, file_data)
                
                # Determine folder structure
                display_path = file_path
                if display_path.startswith('core/src/'):
                    display_path = display_path[9:]
                    folder_base = output_path / "core"
                elif display_path.startswith('plugins/'):
                    display_path = display_path[8:]
                    folder_base = output_path / "plugins"
                else:
                    folder_base = output_path / "other"
                
                # Create folder structure based on module path
                path_parts = display_path.replace('.py', '').split('/')
                module_name = Path(file_path).stem  # Use actual file name
                
                # Create nested folders for the module path
                if len(path_parts) > 1:
                    folder_path = folder_base
                    for part in path_parts[:-1]:  # All parts except the last one
                        folder_path = folder_path / part
                    folder_path.mkdir(parents=True, exist_ok=True)
                    file_output_path = folder_path / f"{module_name}.md"
                else:
                    folder_base.mkdir(parents=True, exist_ok=True)
                    file_output_path = folder_base / f"{module_name}.md"
                
                # Store mapping for cross-references
                self.output_file_mapping[file_path] = str(file_output_path).replace('\\', '/')
                generated_files[file_path] = (content, file_output_path)
        
        # Second pass: Add cross-references and write files
        for file_path, (content, output_file_path) in generated_files.items():
            # Post-process content to add proper cross-references
            processed_content = self.add_cross_references_post_generation(content, str(output_file_path).replace('\\', '/'))
            # Also process field references
            lines = processed_content.split('\n')
            processed_lines = []
            for line in lines:
                if line.strip().startswith('- `') and ':' in line:
                    # This is likely a field line - reprocess it
                    field_match = re.match(r'^(\s*)- `([^`]+)`(.*)$', line)
                    if field_match:
                        indent, field_content, rest = field_match.groups()
                        processed_lines.append(f"{indent}- {field_content}{rest}")
                    else:
                        processed_lines.append(line)
                else:
                    processed_lines.append(line)
            
            final_content = '\n'.join(processed_lines)
            
            with open(output_file_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            total_items = sum(len(entries) for entries in modules[file_path].values())
            print(f"Generated {output_file_path} with {total_items} entries")
        
        # Generate index file
        index_content = self.generate_index_file(modules, output_path)
        index_path = output_path / "index.md"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        print(f"Generated {index_path}")
        
        print(f"\nDocumentation generated in {output_path}")
        print(f"Total entries: {len(self.doc_entries)}")
        print(f"Total modules: {len(modules)}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract REQUIRED docstrings and generate Docusaurus docs")
    parser.add_argument("--root", "-r", default=".", help="Root directory of the UTCP project")
    parser.add_argument("--output", "-o", default="./docs", help="Output directory for generated docs")
    parser.add_argument("--dirs", "-d", nargs="+", default=["core", "plugins"],
                        help="Directories to scan (default: core plugins)")
    
    args = parser.parse_args()
    
    extractor = RequiredDocExtractor(args.root)
    
    print(f"Scanning directories: {args.dirs}")
    extractor.scan_directories(args.dirs)
    
    if not extractor.doc_entries:
        print("No REQUIRED docstrings found!")
        return
    
    print(f"Found {len(extractor.doc_entries)} REQUIRED docstrings")
    extractor.generate_docs(args.output)


if __name__ == "__main__":
    main()
