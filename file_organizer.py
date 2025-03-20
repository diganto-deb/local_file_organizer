#!/usr/bin/env python3
from mcp.server.fastmcp import FastMCP, Context
import os
from pathlib import Path
import logging
import functools
from typing import Dict, List, Optional, Set, Tuple, Union, Callable, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create an MCP server
mcp = FastMCP("File Organizer")

# File type categories and their extensions
CATEGORIES = {
    'Documents': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.md', '.html', '.json', '.ttl', '.csv', '.xlsx', '.pptx', '.tex', '.pages', '.key', '.numbers'},
    'Images': {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.heic', '.tiff', '.bmp', '.raw'},
    'Videos': {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v'},
    'Audio': {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.wma', '.aiff'},
    'Archives': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso', '.dmg'},
    'Code': {'.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.h', '.php', '.rb', '.go', '.rs', '.jsx', '.ts', '.tsx', '.vsix', '.swift', '.kt', '.scala', '.vue'},
    'Applications': {'.dmg', '.app', '.exe', '.msi', '.deb', '.rpm', '.apk', '.pkg'}
}
OTHER_CATEGORY = 'Others'

# Common project indicators
PROJECT_INDICATORS = {
    'files': {
        '.git', '.gitignore', 'package.json', 'requirements.txt', 'Makefile', 'CMakeLists.txt', 
        'build.gradle', 'pom.xml', 'Gemfile', 'Cargo.toml', 'setup.py', 'Pipfile', 'docker-compose.yml',
        'Dockerfile', '.env', 'tsconfig.json', 'webpack.config.js', 'composer.json', 'build.sbt',
        'project.clj', 'mix.exs', 'pubspec.yaml', 'yarn.lock', 'package-lock.json'
    },
    'directories': {
        '.git', 'node_modules', 'src', 'test', 'tests', 'docs', 'bin', 'build', 'dist', 'target',
        '.idea', '.vscode', '__pycache__', 'venv', 'env', '.env', '.mvn'
    }
}

# Common excluded directories for searches and recursive operations
EXCLUDED_DIRS = ['.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env']

# Helper function to get file category
def get_file_category(file_path: str) -> str:
    """Determine the category for a file based on its extension."""
    file_extension = Path(file_path).suffix.lower()
    for category, extensions in CATEGORIES.items():
        if file_extension in extensions:
            return category
    return OTHER_CATEGORY

# Helper function to process directory listing
def process_dir_listing(dir_content: str) -> tuple[list[str], list[str]]:
    """Process directory listing output into files and directories lists"""
    if not dir_content:
        return [], []
        
    files = [line.replace('[FILE] ', '') for line in dir_content.split('\n') 
             if line.strip() and line.startswith('[FILE]')]
    
    dirs = [line.replace('[DIR] ', '') for line in dir_content.split('\n') 
            if line.strip() and line.startswith('[DIR]')]
    
    return files, dirs

# Helper function to format file sizes
def format_size(size_bytes: int) -> str:
    """Convert size in bytes to appropriate unit with formatting"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

# Helper function to detect if a directory is a project directory
def is_project_directory(dir_path: str, ctx: Context) -> bool:
    """
    Determine if a directory appears to be a project directory.
    
    Args:
        dir_path: Path to check
        ctx: MCP context
        
    Returns:
        True if directory appears to be a project, False otherwise
    """
    try:
        # Get directory content
        dir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": dir_path})
        files, dirs = process_dir_listing(dir_content)
        
        # Check for project indicator files
        for file_name in files:
            if file_name.lower() in PROJECT_INDICATORS['files']:
                logger.info(f"Project indicator file found: {file_name} in {dir_path}")
                return True
                
        # Check for project indicator directories
        for dir_name in dirs:
            if dir_name.lower() in PROJECT_INDICATORS['directories']:
                logger.info(f"Project indicator directory found: {dir_name} in {dir_path}")
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking if {dir_path} is a project directory: {e}")
        return False  # If in doubt, consider it's not a project directory

# Decorator to verify directory access
def verify_access(func: Callable) -> Callable:
    """Decorator to verify if a directory/file is accessible by the MCP server"""
    @functools.wraps(func)
    def wrapper(path: str, *args, **kwargs) -> str:
        # Extract context from kwargs or use current request context
        ctx = kwargs.get('ctx')
        
        try:
            allowed_dirs = ctx.call_tool("mcp_filesystem_list_allowed_directories", {})
            
            is_allowed = False
            for allowed_dir in allowed_dirs.split('\n'):
                if allowed_dir.strip() and path.startswith(allowed_dir.strip()):
                    is_allowed = True
                    break
                    
            if not is_allowed:
                return f"Warning: {path} is NOT in the allowed directories list"
                
            return func(path, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error verifying access for {path}: {e}")
            return f"Error: {str(e)}"
    
    return wrapper

@mcp.tool()
def list_categories() -> str:
    """List all file categories supported by the organizer"""
    categories = list(CATEGORIES.keys()) + [OTHER_CATEGORY]
    return "Available file categories:\n" + "\n".join(f"- {category}" for category in categories)

@mcp.tool()
def list_allowed_directories(ctx: Context) -> str:
    """List all directories the MCP server is allowed to access"""
    try:
        result = ctx.call_tool("mcp_filesystem_list_allowed_directories", {})
        logger.info("Listed allowed directories")
        return f"Allowed directories:\n{result}"
    except Exception as e:
        logger.error(f"Error listing allowed directories: {e}")
        return f"Error: {str(e)}"

@mcp.tool()
@verify_access
def create_category_directories(path: str, ctx: Context) -> str:
    """Create category directories for file organization
    
    Args:
        path: Base directory where category folders will be created
        ctx: MCP context
    
    Returns:
        Summary of created directories
    """
    # Create all category directories
    categories = list(CATEGORIES.keys()) + [OTHER_CATEGORY]
    created_dirs = []
    
    for category in categories:
        category_dir = os.path.join(path, category)
        try:
            ctx.call_tool("mcp_filesystem_create_directory", {"path": category_dir})
            created_dirs.append(category)
        except Exception as e:
            logger.error(f"Error creating {category} directory: {e}")
    
    return f"Created category directories in {path}:\n" + "\n".join(f"- {dir}" for dir in created_dirs)

@mcp.tool()
@verify_access
def list_directory_files(path: str, ctx: Context) -> str:
    """List all files in a directory
    
    Args:
        path: Directory to list
        ctx: MCP context
        
    Returns:
        Formatted list of files and directories
    """
    result = ctx.call_tool("mcp_filesystem_list_directory", {"path": path})
    return f"Contents of {path}:\n{result}"

@mcp.tool()
@verify_access
def analyze_directory(path: str, recursive: bool = False, max_depth: int = 2, ctx: Context = None) -> str:
    """Analyze files in a directory by categorizing them without moving anything
    
    Args:
        path: Directory to analyze
        recursive: Whether to analyze subdirectories recursively
        max_depth: Maximum recursion depth (1=current dir only, 2=one level down, etc.)
        ctx: MCP context
        
    Returns:
        Analysis summary with file categories
    """
    def _analyze_dir_recursive(current_path: str, relative_path: str = "", current_depth: int = 1):
        """Helper function to analyze directory recursively with depth control"""
        nonlocal directories_processed
        
        # Get directory listing
        dir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": current_path})
        files, dirs = process_dir_listing(dir_content)
        
        # Count this directory
        directories_processed += 1
        
        # Process files in the current directory
        for file_name in files:
            # Skip files that are already category directories
            if file_name in CATEGORIES or file_name == OTHER_CATEGORY:
                continue
                
            category = get_file_category(file_name)
            file_path = os.path.join(relative_path, file_name) if relative_path else file_name
            categorized[category].append(file_path)
        
        # Only recurse if we haven't reached max depth
        if current_depth < max_depth:
            for dir_name in dirs:
                # Skip category directories and system directories
                if dir_name in CATEGORIES or dir_name == OTHER_CATEGORY or dir_name in EXCLUDED_DIRS:
                    continue
                    
                subdir_path = os.path.join(current_path, dir_name)
                subdir_rel_path = os.path.join(relative_path, dir_name) if relative_path else dir_name
                
                try:
                    _analyze_dir_recursive(subdir_path, subdir_rel_path, current_depth + 1)
                except Exception as e:
                    logger.error(f"Error processing subdirectory {subdir_path}: {e}")
    
    # Track files by category
    categorized = {cat: [] for cat in CATEGORIES.keys()}
    categorized[OTHER_CATEGORY] = []
    directories_processed = 0
    
    if recursive:
        _analyze_dir_recursive(path)
    else:
        # Non-recursive analysis
        dir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": path})
        files, _ = process_dir_listing(dir_content)
        directories_processed = 1
        
        # Process files in the current directory only
        for file_name in files:
            # Skip files that are already category directories
            if file_name in CATEGORIES or file_name == OTHER_CATEGORY:
                continue
                
            category = get_file_category(file_name)
            categorized[category].append(file_name)
    
    # Generate summary
    summary = [f"{'Recursive ' if recursive else ''}Directory Analysis Summary:"]
    if recursive:
        summary.append(f"Base directory: {path}")
        summary.append(f"Total subdirectories processed: {directories_processed}")
        if max_depth < 999:
            summary.append(f"Maximum depth: {max_depth} levels")
    
    total_files = sum(len(files) for files in categorized.values())
    summary.append(f"Total Files: {total_files}")
    summary.append("")
    
    # Report files by category
    for category, files in categorized.items():
        if files:
            summary.append(f"{category}: {len(files)} files")
            # Sort files for better readability
            sorted_files = sorted(files)
            max_examples = 10 if recursive else 5
            for file in sorted_files[:max_examples]:
                summary.append(f"  - {file}")
            if len(files) > max_examples:
                summary.append(f"  - ... and {len(files) - max_examples} more")
            summary.append("")
                
    return "\n".join(summary)

@mcp.tool()
@verify_access
def organize_files(path: str, confirm: bool = False, respect_projects: bool = True, ctx: Context = None) -> str:
    """Organize files into category directories based on their extensions
    
    Args:
        path: Base directory where files will be organized
        confirm: If True, actually move files; if False, just show plan
        respect_projects: If True, don't move files from directories that appear to be projects
        ctx: MCP context
        
    Returns:
        Summary of organized files or operation plan
    """
    # If not confirmed, just return analysis
    if not confirm:
        return (
            f"This operation will organize files in {path} into category subdirectories.\n"
            f"To see what would be moved without making changes, use the analyze_directory tool.\n"
            f"Project directories will {'be respected (files will not be moved from them)' if respect_projects else 'not be respected'}.\n"
            f"To proceed with organizing files, call this function again with confirm=True."
        )
    
    # Use the bulk move functionality with no specific category or extension filters
    return bulk_move_files(path, respect_projects=respect_projects, ctx=ctx)

@mcp.tool()
@verify_access
def search_files(path: str, pattern: str, ctx: Context = None) -> str:
    """Search for files matching a pattern in the specified directory
    
    Args:
        path: Directory to search in
        pattern: Search pattern (glob format)
        ctx: MCP context
        
    Returns:
        List of matching files
    """
    result = ctx.call_tool("mcp_filesystem_search_files", {
        "path": path,
        "pattern": pattern,
        "excludePatterns": EXCLUDED_DIRS
    })
    
    if not result:
        return f"No files matching '{pattern}' found in {path}"
        
    return f"Found files matching '{pattern}' in {path}:\n{result}"

@mcp.tool()
@verify_access
def get_metadata(path: str, include_stats: bool = True, ctx: Context = None) -> str:
    """Get detailed metadata about a file or directory
    
    Args:
        path: Path to the file or directory to analyze
        include_stats: For directories, whether to include file statistics
        ctx: MCP context
        
    Returns:
        Formatted string with metadata information
    """
    # Get basic file info
    basic_info = ctx.call_tool("mcp_filesystem_get_file_info", {"path": path})
    
    # Extract info to determine if it's a directory
    is_directory = "isDirectory: true" in basic_info
    
    metadata = []
    
    # Add common info
    metadata.append(f"{'Directory' if is_directory else 'File'} Metadata:")
    metadata.append(f"Path: {path}")
    
    if not is_directory:
        # Add file-specific info
        file_name = os.path.basename(path)
        file_category = get_file_category(path)
        metadata.append(f"Name: {file_name}")
        metadata.append(f"Category: {file_category}")
    
    # Add the basic metadata from get_file_info
    for line in basic_info.split('\n'):
        if line and not line.startswith("isDirectory") and not line.startswith("isFile"):
            # Clean up and format the metadata line
            key, value = line.split(': ', 1) if ': ' in line else (line, "")
            
            # Convert size to readable format if this is the size field
            if key.lower() == 'size':
                try:
                    size_bytes = int(value.strip())
                    value = format_size(size_bytes)
                except ValueError:
                    pass  # Keep original value if conversion fails
                    
            metadata.append(f"{key.capitalize()}: {value}")
    
    # For directories, add content summary
    if is_directory:
        dir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": path})
        files, dirs = process_dir_listing(dir_content)
        
        metadata.append(f"Total files: {len(files)}")
        metadata.append(f"Total subdirectories: {len(dirs)}")
        
        # If stats are requested for a directory
        if include_stats and files:
            # Group files by category
            file_by_category = {cat: [] for cat in CATEGORIES.keys()}
            file_by_category[OTHER_CATEGORY] = []
            
            # Batch file info retrieval for efficiency
            file_paths = [os.path.join(path, file_name) for file_name in files]
            
            # Use read_multiple_files instead of individual calls when possible
            file_sizes = {}
            
            # Process each file
            for i, file_name in enumerate(files):
                # Get file category
                category = get_file_category(file_name)
                file_by_category[category].append(file_name)
                
                # Get file size
                file_path = os.path.join(path, file_name)
                try:
                    file_info = ctx.call_tool("mcp_filesystem_get_file_info", {"path": file_path})
                    
                    # Extract size
                    for line in file_info.split('\n'):
                        if line.startswith('size:'):
                            size_str = line.replace('size:', '').strip()
                            file_sizes[file_name] = int(size_str)
                            break
                except Exception as e:
                    logger.error(f"Error getting info for {file_path}: {e}")
            
            # Add file type statistics
            metadata.append("\nFile Categories:")
            for category, category_files in file_by_category.items():
                if category_files:
                    metadata.append(f"{category}: {len(category_files)} files")
                    # Show examples
                    for file in sorted(category_files)[:3]:
                        size_info = f" ({format_size(file_sizes.get(file, 0))})" if file in file_sizes else ""
                        metadata.append(f"  - {file}{size_info}")
                    if len(category_files) > 3:
                        metadata.append(f"  - ... and {len(category_files) - 3} more")
            
            # Add size information
            if file_sizes:
                total_size = sum(file_sizes.values())
                largest_files = sorted(file_sizes.items(), key=lambda x: x[1], reverse=True)[:5]
                
                metadata.append(f"\nTotal size: {format_size(total_size)}")
                metadata.append("Largest files:")
                for file_name, size in largest_files:
                    metadata.append(f"  - {file_name}: {format_size(size)}")
        
        # List subdirectories with their sizes
        if dirs:
            metadata.append("\nSubdirectories:")
            subdir_sizes = {}
            
            # Get size for each subdirectory (could batch this in future versions)
            for subdir in dirs:
                subdir_path = os.path.join(path, subdir)
                try:
                    subdir_info = ctx.call_tool("mcp_filesystem_get_file_info", {"path": subdir_path})
                    for line in subdir_info.split('\n'):
                        if line.startswith('size:'):
                            size_str = line.replace('size:', '').strip()
                            subdir_sizes[subdir] = int(size_str)
                            break
                except Exception as e:
                    logger.error(f"Error getting size for {subdir_path}: {e}")
                    subdir_sizes[subdir] = 0
            
            # Display subdirectories sorted alphabetically with their sizes
            for subdir in sorted(dirs):
                size_info = f" ({format_size(subdir_sizes.get(subdir, 0))})"
                metadata.append(f"  - {subdir}{size_info}")
    
    return "\n".join(metadata)

@mcp.tool()
@verify_access
def read_file_content(path: str, ctx: Context = None) -> str:
    """Read the contents of a file
    
    Args:
        path: Path to the file to read
        ctx: MCP context
        
    Returns:
        File contents as string
    """
    result = ctx.call_tool("mcp_filesystem_read_file", {"path": path})
    return f"Contents of {path}:\n{result}"

@mcp.tool()
@verify_access
def analyze_project_directories(path: str, ctx: Context = None) -> str:
    """Identify directories that appear to be projects based on common indicators
    
    Args:
        path: Base directory to analyze
        ctx: MCP context
        
    Returns:
        List of identified project directories and indicators found
    """
    # Get directory listing
    dir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": path})
    _, dirs = process_dir_listing(dir_content)
    
    # Track project directories and their indicators
    project_dirs = {}
    
    # Process subdirectories
    for dir_name in dirs:
        # Skip category directories
        if dir_name in CATEGORIES or dir_name == OTHER_CATEGORY:
            continue
        
        dir_path = os.path.join(path, dir_name)
        
        # Check for project indicators
        indicators_found = []
        try:
            subdir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": dir_path})
            sub_files, sub_dirs = process_dir_listing(subdir_content)
            
            # Check files
            for file_name in sub_files:
                if file_name.lower() in PROJECT_INDICATORS['files']:
                    indicators_found.append(f"File: {file_name}")
            
            # Check directories
            for subdir_name in sub_dirs:
                if subdir_name.lower() in PROJECT_INDICATORS['directories']:
                    indicators_found.append(f"Directory: {subdir_name}")
            
            if indicators_found:
                project_dirs[dir_name] = indicators_found
        except Exception as e:
            logger.error(f"Error analyzing subdirectory {dir_path}: {e}")
    
    # Generate report
    if not project_dirs:
        return f"No project directories identified in {path}"
    
    summary = [f"Project Directories in {path}:"]
    for dir_name, indicators in project_dirs.items():
        summary.append(f"\n{dir_name}:")
        summary.append("  Project indicators found:")
        for indicator in indicators:
            summary.append(f"    - {indicator}")
    
    return "\n".join(summary)

@mcp.tool()
@verify_access
def bulk_move_files(path: str, category: str = None, file_extension: str = None, 
                   respect_projects: bool = True, ctx: Context = None) -> str:
    """Move multiple files of the same type to their category directory in a single operation
    
    Args:
        path: Base directory where files will be organized
        category: Specific category to organize (if None, will organize files by their detected category)
        file_extension: Specific file extension to organize (e.g. '.mp4', '.pdf')
        respect_projects: If True, don't move files from directories that appear to be projects
        ctx: MCP context
        
    Returns:
        Summary of moved files
    """
    # Ensure category directories exist
    create_category_directories(path, ctx=ctx)
    
    # Get directory listing
    dir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": path})
    files, dirs = process_dir_listing(dir_content)
    
    # Track files to be moved
    files_by_category = {cat: [] for cat in CATEGORIES.keys()}
    files_by_category[OTHER_CATEGORY] = []
    project_dirs = []
    skipped = []
    
    # First identify project directories if needed
    if respect_projects:
        for dir_name in dirs:
            # Skip category directories
            if dir_name in CATEGORIES or dir_name == OTHER_CATEGORY:
                continue
            
            dir_path = os.path.join(path, dir_name)
            
            # Check if it's a project directory
            if is_project_directory(dir_path, ctx):
                project_dirs.append(dir_name)
    
    # Process files in root directory
    for file_name in files:
        # Skip files that are category directories
        if file_name in CATEGORIES or file_name == OTHER_CATEGORY:
            skipped.append(file_name)
            continue
            
        # Filter by extension if specified
        if file_extension and not file_name.lower().endswith(file_extension.lower()):
            continue
            
        detected_category = get_file_category(file_name)
        
        # Filter by category if specified
        if category and category != detected_category:
            continue
            
        # Add to the appropriate category list
        file_path = os.path.join(path, file_name)
        files_by_category[detected_category].append((file_path, file_name))
    
    # For non-project subdirectories, collect their files too
    if respect_projects:
        non_project_dirs = [d for d in dirs if d not in CATEGORIES and 
                           d != OTHER_CATEGORY and 
                           d not in project_dirs and
                           d not in EXCLUDED_DIRS]
        
        for dir_name in non_project_dirs:
            dir_path = os.path.join(path, dir_name)
            
            # Process non-project directory files
            try:
                subdir_content = ctx.call_tool("mcp_filesystem_list_directory", {"path": dir_path})
                subdir_files, _ = process_dir_listing(subdir_content)
                
                for file_name in subdir_files:
                    # Filter by extension if specified
                    if file_extension and not file_name.lower().endswith(file_extension.lower()):
                        continue
                        
                    detected_category = get_file_category(file_name)
                    
                    # Filter by category if specified
                    if category and category != detected_category:
                        continue
                        
                    # Add to the appropriate category list
                    file_path = os.path.join(dir_path, file_name)
                    display_name = f"{dir_name}/{file_name}"
                    files_by_category[detected_category].append((file_path, display_name))
            except Exception as e:
                logger.error(f"Error processing subdirectory {dir_path}: {e}")
    
    # Now move the files in bulk by category
    moved_count = 0
    errors = []
    organized = {cat: [] for cat in CATEGORIES.keys()}
    organized[OTHER_CATEGORY] = []
    
    # Process each category
    for cat, file_list in files_by_category.items():
        if not file_list:
            continue
            
        # Create summary of what's being moved
        logger.info(f"Moving {len(file_list)} files to {cat} category")
        
        # Move each file in this category
        for file_path, display_name in file_list:
            destination = os.path.join(path, cat, os.path.basename(file_path))
            try:
                ctx.call_tool("mcp_filesystem_move_file", {
                    "source": file_path,
                    "destination": destination
                })
                organized[cat].append(display_name)
                moved_count += 1
            except Exception as e:
                errors.append(f"{os.path.basename(file_path)}: {str(e)}")
                logger.error(f"Error moving {file_path}: {e}")
    
    # Generate summary
    summary = ["Bulk Organization Summary:"]
    summary.append(f"Total files moved: {moved_count}")
    
    # Report organized files by category
    for cat, files in organized.items():
        if files:
            summary.append(f"\n{category or cat}: {len(files)} files")
            for file in files[:5]:  # Show up to 5 examples
                summary.append(f"  - {file}")
            if len(files) > 5:
                summary.append(f"  - ... and {len(files) - 5} more")
    
    # Report errors
    if errors:
        summary.append(f"\nErrors ({len(errors)}):")
        for i, error in enumerate(errors[:5]):
            summary.append(f"  - {error}")
        if len(errors) > 5:
            summary.append(f"  - ... and {len(errors) - 5} more errors")
    
    # Report project directories found
    if respect_projects and project_dirs:
        summary.append(f"\nIdentified project directories (contents preserved):")
        for dir_name in project_dirs:
            summary.append(f"  - {dir_name}")
    
    return "\n".join(summary)

if __name__ == "__main__":
    # Run the MCP server
    mcp.run() 