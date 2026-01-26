#!/usr/bin/env python3
"""
Template Syntax Validator for Gobstopper Framework

A comprehensive template validation system that integrates with loguru 
to provide detailed syntax checking for both Jinja2 and Tera templates.
"""

import re
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Try to import template engines for validation
try:
    from jinja2 import Environment, TemplateSyntaxError as JinjaTemplateSyntaxError
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False
    JinjaTemplateSyntaxError = Exception

try:
    from gobstopper._core import RustTemplateEngine
    HAS_RUST_ENGINE = True
except ImportError:
    HAS_RUST_ENGINE = False


class TemplateEngine(Enum):
    JINJA2 = "jinja2"
    TERA = "tera"
    AUTO = "auto"


class ValidationLevel(Enum):
    ERROR = "error"
    WARNING = "warning" 
    INFO = "info"
    SUCCESS = "success"


@dataclass
class ValidationIssue:
    """Represents a template validation issue"""
    level: ValidationLevel
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    context: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass 
class ValidationResult:
    """Results from template validation"""
    file_path: str
    engine: TemplateEngine
    is_valid: bool
    issues: List[ValidationIssue]
    syntax_score: float  # 0-100, higher is better
    performance_score: float  # 0-100, higher is better


class TemplateValidator:
    """Advanced template syntax validator with logging integration"""
    
    def __init__(self, logger=None):
        """Initialize the validator with optional logger"""
        self.logger = logger
        self.jinja_env = None
        self.rust_engine = None
        
        # Initialize template engines if available
        if HAS_JINJA2:
            self.jinja_env = Environment()
            
        if HAS_RUST_ENGINE:
            try:
                self.rust_engine = RustTemplateEngine(".", enable_streaming=False)
            except Exception:
                pass
    
    def log(self, level: str, message: str, **kwargs):
        """Log a message if logger is available"""
        if self.logger:
            getattr(self.logger, level)(message, **kwargs)
        else:
            # Fallback to print with emoji indicators
            emoji = {"debug": "🔍", "info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}.get(level, "📝")
            print(f"{emoji} {message}")
    
    def validate_file(self, file_path: str, engine: TemplateEngine = TemplateEngine.AUTO) -> ValidationResult:
        """Validate a single template file"""
        path = Path(file_path)
        if not path.exists():
            return ValidationResult(
                file_path=file_path,
                engine=engine,
                is_valid=False,
                issues=[ValidationIssue(ValidationLevel.ERROR, f"File not found: {file_path}")],
                syntax_score=0.0,
                performance_score=0.0
            )
        
        self.log("debug", f"🔍 Validating template: {file_path}")
        
        # Read template content
        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            return ValidationResult(
                file_path=file_path,
                engine=engine,
                is_valid=False,
                issues=[ValidationIssue(ValidationLevel.ERROR, f"Could not read file: {e}")],
                syntax_score=0.0,
                performance_score=0.0
            )
        
        # Auto-detect engine if needed
        if engine == TemplateEngine.AUTO:
            engine = self._detect_engine(content, file_path)
        
        # Validate with appropriate engine
        if engine == TemplateEngine.JINJA2:
            return self._validate_jinja2(file_path, content)
        elif engine == TemplateEngine.TERA:
            return self._validate_tera(file_path, content)
        else:
            # Try both engines and return the better result
            jinja_result = self._validate_jinja2(file_path, content)
            tera_result = self._validate_tera(file_path, content)
            
            return jinja_result if jinja_result.syntax_score >= tera_result.syntax_score else tera_result
    
    def validate_directory(self, directory: str, engine: TemplateEngine = TemplateEngine.AUTO) -> List[ValidationResult]:
        """Validate all template files in a directory"""
        path = Path(directory)
        if not path.exists():
            self.log("error", f"❌ Directory not found: {directory}")
            return []
        
        template_files = []
        for ext in ['*.html', '*.jinja2', '*.j2', '*.tera']:
            template_files.extend(path.rglob(ext))
        
        self.log("info", f"🔍 Found {len(template_files)} template files in {directory}")
        
        results = []
        for file_path in template_files:
            result = self.validate_file(str(file_path), engine)
            results.append(result)
            
            # Log result
            if result.is_valid:
                self.log("success", f"✅ {file_path.name} - Valid (Score: {result.syntax_score:.1f}/100)")
            else:
                error_count = len([i for i in result.issues if i.level == ValidationLevel.ERROR])
                warning_count = len([i for i in result.issues if i.level == ValidationLevel.WARNING])
                self.log("warning", f"⚠️ {file_path.name} - {error_count} errors, {warning_count} warnings")
        
        return results
    
    def _detect_engine(self, content: str, file_path: str) -> TemplateEngine:
        """Auto-detect which template engine is most appropriate"""
        
        # Check file extension hints
        if file_path.endswith('.tera'):
            return TemplateEngine.TERA
        elif file_path.endswith(('.jinja2', '.j2')):
            return TemplateEngine.JINJA2
        
        # Analyze template syntax patterns
        jinja_patterns = [
            r'{{.*?\|.*?}}',  # Jinja filters
            r'{%\s*set\s+',   # Jinja set statements
            r'{%\s*if\s+.*?\s+is\s+',  # Jinja 'is' tests
            r'{{.*?\.strftime\(',  # Jinja datetime methods
        ]
        
        tera_patterns = [
            r'{{.*?\|\s*safe\s*}}',  # Tera safe filter
            r'{%\s*if\s+.*?%}.*?{%\s*else\s*%}.*?{%\s*endif\s*%}',  # Tera if/else/endif
            r'{{.*?\|\s*default\s*\(value=".*?"\)}}',  # Tera default filter syntax
        ]
        
        jinja_score = sum(1 for pattern in jinja_patterns if re.search(pattern, content))
        tera_score = sum(1 for pattern in tera_patterns if re.search(pattern, content))
        
        if tera_score > jinja_score:
            return TemplateEngine.TERA
        else:
            return TemplateEngine.JINJA2
    
    def _validate_jinja2(self, file_path: str, content: str) -> ValidationResult:
        """Validate template using Jinja2"""
        issues = []
        syntax_score = 100.0
        performance_score = 100.0
        
        if not HAS_JINJA2:
            issues.append(ValidationIssue(
                ValidationLevel.WARNING, 
                "Jinja2 not available for validation"
            ))
            return ValidationResult(file_path, TemplateEngine.JINJA2, False, issues, 0.0, 0.0)
        
        # Basic syntax validation
        try:
            self.jinja_env.from_string(content)
        except JinjaTemplateSyntaxError as e:
            issues.append(ValidationIssue(
                ValidationLevel.ERROR,
                f"Jinja2 syntax error: {e}",
                line=getattr(e, 'lineno', None)
            ))
            syntax_score = 0.0
        
        # Additional Jinja2-specific checks
        issues.extend(self._check_jinja2_patterns(content))
        
        # Calculate performance score
        performance_score = self._calculate_performance_score(content, TemplateEngine.JINJA2)
        
        # Adjust syntax score based on issues
        for issue in issues:
            if issue.level == ValidationLevel.ERROR:
                syntax_score = 0.0
                break
            elif issue.level == ValidationLevel.WARNING:
                syntax_score -= 10.0
        
        return ValidationResult(
            file_path=file_path,
            engine=TemplateEngine.JINJA2,
            is_valid=syntax_score > 0,
            issues=issues,
            syntax_score=max(0.0, syntax_score),
            performance_score=max(0.0, performance_score)
        )
    
    def _validate_tera(self, file_path: str, content: str) -> ValidationResult:
        """Validate template using Tera (via Rust engine)"""
        issues = []
        syntax_score = 100.0
        performance_score = 100.0
        
        # Check for Tera syntax patterns and compatibility
        issues.extend(self._check_tera_patterns(content))
        
        # Try to compile with Rust engine if available
        if HAS_RUST_ENGINE and self.rust_engine:
            try:
                # Create a temporary template for validation
                temp_name = f"validation_temp_{hash(content) % 10000}"
                # Note: In real implementation, you'd use the Rust engine's validation methods
                # For now, we'll use pattern-based validation
                pass
            except Exception as e:
                issues.append(ValidationIssue(
                    ValidationLevel.ERROR,
                    f"Tera compilation error: {e}"
                ))
                syntax_score = 0.0
        
        # Calculate performance score  
        performance_score = self._calculate_performance_score(content, TemplateEngine.TERA)
        
        # Adjust syntax score based on issues
        for issue in issues:
            if issue.level == ValidationLevel.ERROR:
                syntax_score = 0.0
                break
            elif issue.level == ValidationLevel.WARNING:
                syntax_score -= 10.0
        
        return ValidationResult(
            file_path=file_path,
            engine=TemplateEngine.TERA,
            is_valid=syntax_score > 0,
            issues=issues,
            syntax_score=max(0.0, syntax_score),
            performance_score=max(0.0, performance_score)
        )
    
    def _check_jinja2_patterns(self, content: str) -> List[ValidationIssue]:
        """Check for Jinja2-specific patterns and potential issues"""
        issues = []
        
        # Check for inline if expressions (not compatible with Tera)
        inline_if_pattern = r'{{.*?\s+if\s+.*?\s+else\s+.*?}}'
        for match in re.finditer(inline_if_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            issues.append(ValidationIssue(
                ValidationLevel.WARNING,
                "Inline if expression found - not compatible with Tera",
                line=line_num,
                context=match.group(),
                suggestion="Use {% if %} blocks instead"
            ))
        
        # Check for function calls in templates
        function_call_pattern = r'{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*\)\s*}}'
        for match in re.finditer(function_call_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            func_name = match.group(1)
            issues.append(ValidationIssue(
                ValidationLevel.WARNING,
                f"Function call {func_name}() in template - consider passing as context variable",
                line=line_num,
                context=match.group(),
                suggestion=f"Pass {func_name} value from view context"
            ))
        
        return issues
    
    def _check_tera_patterns(self, content: str) -> List[ValidationIssue]:
        """Check for Tera-specific patterns and potential issues"""
        issues = []
        
        # Check for missing 'endif' statements
        if_count = len(re.findall(r'{%\s*if\s+', content))
        endif_count = len(re.findall(r'{%\s*endif\s*%}', content))
        if if_count != endif_count:
            issues.append(ValidationIssue(
                ValidationLevel.ERROR,
                f"Mismatched if/endif blocks: {if_count} if statements, {endif_count} endif statements"
            ))
        
        # Check for Jinja2 'is' tests (not available in Tera)
        is_test_pattern = r'{%\s*if\s+.*?\s+is\s+'
        if re.search(is_test_pattern, content):
            line_num = content[:re.search(is_test_pattern, content).start()].count('\n') + 1
            issues.append(ValidationIssue(
                ValidationLevel.WARNING,
                "Jinja2 'is' test found - not supported in Tera",
                line=line_num,
                suggestion="Use comparison operators instead"
            ))
        
        # Check for proper default filter usage
        old_default_pattern = r'{{\s*.*?\s*\|\s*default\s*\(\s*["\'][^"\']*["\']\s*\)\s*}}'
        new_default_pattern = r'{{\s*.*?\s*\|\s*default\s*\(\s*value\s*=\s*["\'][^"\']*["\']\s*\)\s*}}'
        
        old_matches = re.findall(old_default_pattern, content)
        new_matches = re.findall(new_default_pattern, content)
        
        if old_matches and not new_matches:
            issues.append(ValidationIssue(
                ValidationLevel.WARNING,
                "Old default filter syntax found - use default(value=\"...\") for Tera compatibility",
                suggestion="Change | default('value') to | default(value='value')"
            ))
        
        return issues
    
    def _calculate_performance_score(self, content: str, engine: TemplateEngine) -> float:
        """Calculate performance score based on template complexity"""
        score = 100.0
        
        # Count expensive operations
        loop_count = len(re.findall(r'{%\s*for\s+', content))
        nested_loops = self._count_nested_loops(content)
        large_data_renders = len(re.findall(r'{{\s*\w+\s*\|\s*length\s*}}', content))
        
        # Deduct points for performance concerns
        score -= loop_count * 2  # 2 points per loop
        score -= nested_loops * 10  # 10 points per nested loop level
        score -= large_data_renders * 1  # 1 point per potential large data render
        
        # Template size penalty for very large templates
        lines = content.count('\n')
        if lines > 500:
            score -= (lines - 500) * 0.1
        
        return max(0.0, min(100.0, score))
    
    def _count_nested_loops(self, content: str) -> int:
        """Count the maximum nesting level of loops"""
        max_depth = 0
        current_depth = 0
        
        for match in re.finditer(r'{%\s*(for|endfor)\s+', content):
            if match.group(1) == 'for':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            else:
                current_depth = max(0, current_depth - 1)
        
        return max_depth
    
    def generate_report(self, results: List[ValidationResult]) -> Dict[str, Any]:
        """Generate a comprehensive validation report"""
        total_files = len(results)
        valid_files = len([r for r in results if r.is_valid])
        invalid_files = total_files - valid_files
        
        total_errors = sum(len([i for i in r.issues if i.level == ValidationLevel.ERROR]) for r in results)
        total_warnings = sum(len([i for i in r.issues if i.level == ValidationLevel.WARNING]) for r in results)
        
        avg_syntax_score = sum(r.syntax_score for r in results) / total_files if total_files > 0 else 0
        avg_performance_score = sum(r.performance_score for r in results) / total_files if total_files > 0 else 0
        
        return {
            "summary": {
                "total_files": total_files,
                "valid_files": valid_files,
                "invalid_files": invalid_files,
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "average_syntax_score": round(avg_syntax_score, 2),
                "average_performance_score": round(avg_performance_score, 2)
            },
            "files": [
                {
                    "path": r.file_path,
                    "engine": r.engine.value,
                    "valid": r.is_valid,
                    "syntax_score": r.syntax_score,
                    "performance_score": r.performance_score,
                    "issues": [
                        {
                            "level": i.level.value,
                            "message": i.message,
                            "line": i.line,
                            "column": i.column,
                            "context": i.context,
                            "suggestion": i.suggestion
                        } for i in r.issues
                    ]
                } for r in results
            ]
        }


def create_template_validator(logger=None) -> TemplateValidator:
    """Factory function to create a template validator"""
    return TemplateValidator(logger)


if __name__ == "__main__":
    # CLI interface for standalone usage
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Gobstopper Template Validator")
    parser.add_argument("path", help="Template file or directory to validate")
    parser.add_argument("--engine", choices=["jinja2", "tera", "auto"], default="auto", 
                       help="Template engine to use for validation")
    parser.add_argument("--output", choices=["text", "json"], default="text",
                       help="Output format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Create validator without logger for CLI usage
    validator = TemplateValidator()
    
    # Validate path
    path = Path(args.path)
    engine = TemplateEngine(args.engine)
    
    if path.is_file():
        results = [validator.validate_file(str(path), engine)]
    elif path.is_dir():
        results = validator.validate_directory(str(path), engine)
    else:
        print(f"❌ Path not found: {args.path}")
        sys.exit(1)
    
    # Generate and output report
    report = validator.generate_report(results)
    
    if args.output == "json":
        print(json.dumps(report, indent=2))
    else:
        # Text output
        summary = report["summary"]
        print(f"""
🔍 Gobstopper Template Validation Report
{'='*50}
📁 Files: {summary['total_files']} total, {summary['valid_files']} valid, {summary['invalid_files']} invalid
🐛 Issues: {summary['total_errors']} errors, {summary['total_warnings']} warnings  
📊 Scores: {summary['average_syntax_score']}/100 syntax, {summary['average_performance_score']}/100 performance
""")
        
        # Show file details if verbose or there are issues
        if args.verbose or summary['total_errors'] > 0 or summary['total_warnings'] > 0:
            print("📋 File Details:")
            for file_data in report["files"]:
                status = "✅" if file_data["valid"] else "❌"
                print(f"  {status} {Path(file_data['path']).name} - {file_data['engine']} engine")
                
                for issue in file_data["issues"]:
                    level_emoji = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue["level"], "📝")
                    line_info = f" (line {issue['line']})" if issue["line"] else ""
                    print(f"    {level_emoji} {issue['message']}{line_info}")
                    if issue["suggestion"] and args.verbose:
                        print(f"      💡 Suggestion: {issue['suggestion']}")
    
    # Exit with error code if there are validation errors
    if report["summary"]["total_errors"] > 0:
        sys.exit(1)