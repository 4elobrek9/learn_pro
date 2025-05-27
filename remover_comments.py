import re
import os
import sys
import shutil
from datetime import datetime
import tokenize
from io import StringIO

# --- Вспомогательные функции для очистки ---

def _clean_python_code(content, compact_mode=False):
    """
    Удаляет комментарии и docstrings из Python кода.
    В зависимости от compact_mode, либо оставляет отступы и пустые строки, либо максимально сжимает.
    """
    cleaned_tokens = []
    
    try:
        f = StringIO(content)

        last_token_end_row = 1
        last_token_end_col = 0

        for toktype, tokstr, (srow, scol), (erow, ecol), line_text in tokenize.generate_tokens(f.readline):
            # Skip comments
            if toktype == tokenize.COMMENT:
                continue 

            # Skip potential docstrings if they are the only thing on the line
            if toktype == tokenize.STRING and (tokstr.startswith('"""') or tokstr.startswith("'''")):
                if line_text.strip() == tokstr.strip():
                    continue

            # Add implicit newlines if tokens are on different lines but no NEWLINE token was seen
            # This helps preserve vertical spacing between logical blocks in readable mode
            if srow > last_token_end_row and not compact_mode:
                cleaned_tokens.append((tokenize.NEWLINE, '\n', (last_token_end_row, last_token_end_col), (srow, 0), ''))
                last_token_end_col = 0 # Reset column for new line

            # In readable mode, add spaces for indentation or gaps between tokens
            if scol > last_token_end_col and srow == last_token_end_row and not compact_mode:
                cleaned_tokens.append((tokenize.INDENT, ' ' * (scol - last_token_end_col), (srow, last_token_end_col), (srow, scol), ''))
            
            # Append the actual token
            cleaned_tokens.append((toktype, tokstr, (srow, scol), (erow, ecol), line_text))
            
            last_token_end_row = erow
            last_token_end_col = ecol

        # Reconstruct the code from the filtered tokens
        reconstructed_content = []
        last_line_num = 0
        last_col_num = 0

        for token in cleaned_tokens:
            tok_type, tok_string, (srow, scol), (erow, ecol), _ = token

            if compact_mode:
                # In compact mode for Python, we join tokens without extra spaces or newlines
                # The tokenizer handles essential spacing/syntax
                if tok_type == tokenize.NEWLINE:
                    if reconstructed_content and reconstructed_content[-1] != '\n':
                        reconstructed_content.append('\n')
                elif tok_type not in [tokenize.INDENT, tokenize.DEDENT]:
                    reconstructed_content.append(tok_string)
            else: # Readable mode
                # Add newlines for line breaks
                if srow > last_line_num:
                    reconstructed_content.append('\n' * (srow - last_line_num))
                    last_col_num = 0 # Reset column for new line

                # Add spaces for indentation or gaps between tokens
                if scol > last_col_num:
                    reconstructed_content.append(' ' * (scol - last_col_num))
                
                reconstructed_content.append(tok_string)

            last_line_num = erow
            last_col_num = ecol

        cleaned_content_str = "".join(reconstructed_content)

    except tokenize.TokenError as e:
        print(f"Предупреждение: Ошибка токенизации Python файла. Возможно, синтаксическая ошибка. Переход к fallback-методу: {e}")
        return _clean_python_code_fallback_regex(content, compact_mode)
    except Exception as e:
        print(f"Предупреждение: Непредвиденная ошибка при токенизации Python файла. Переход к fallback-методу: {e}")
        return _clean_python_code_fallback_regex(content, compact_mode)

    # Final cleanup regardless of mode
    if compact_mode:
        cleaned_content_str = re.sub(r'\n+', '\n', cleaned_content_str).strip() # Consolidate newlines
        # For Python compact, we still aggressively remove internal whitespace as tokenization handles syntax
        cleaned_content_str = re.sub(r'\s+', '', cleaned_content_str).strip()
    else: # Readable mode
        cleaned_content_str = re.sub(r'\n{3,}', '\n\n', cleaned_content_str) # Max two newlines
        cleaned_content_str = re.sub(r'[ \t]+$', '', cleaned_content_str, flags=re.MULTILINE) # Remove trailing whitespace
        cleaned_content_str = cleaned_content_str.strip() # Remove leading/trailing blank lines in file
        
    return cleaned_content_str

def _clean_python_code_fallback_regex(content, compact_mode=False):
    """Fallback for Python using regex (less reliable but won't crash on some token errors)."""
    lines = content.splitlines()
    cleaned_lines = []
    in_multiline_string = False

    for line in lines:
        original_line_stripped = line.strip()

        triple_quote_patterns = ['"""', "'''"]
        for pattern in triple_quote_patterns:
            if original_line_stripped.startswith(pattern):
                if original_line_stripped.count(pattern) % 2 == 1:
                    in_multiline_string = not in_multiline_string
                break
        
        if in_multeline_string:
            continue

        if original_line_stripped.startswith('#'):
            continue

        match = re.search(r'#', line)
        if match:
            pre_comment_part = line[:match.start()]
            single_quotes_odd = (pre_comment_part.count("'") - pre_comment_part.count("\\'")) % 2 == 1
            double_quotes_odd = (pre_comment_part.count('"') - pre_comment_part.count('\\"')) % 2 == 1
            
            if single_quotes_odd or double_quotes_odd:
                cleaned_lines.append(line)
            else:
                cleaned_lines.append(line[:match.start()].rstrip())
        else:
            cleaned_lines.append(line)
    
    cleaned_content_str = "\n".join(cleaned_lines)
    cleaned_content_str = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', '', cleaned_content_str)

    if compact_mode:
        cleaned_content_str = re.sub(r'\s+', '', cleaned_content_str).strip() 
    else:
        cleaned_content_str = re.sub(r'\n{3,}', '\n\n', cleaned_content_str)
        cleaned_content_str = re.sub(r'[ \t]+$', '', cleaned_content_str, flags=re.MULTILINE)
        cleaned_content_str = cleaned_content_str.strip()
    return cleaned_content_str


def _clean_html_js_css_code(content, compact_mode=False):
    """
    Удаляет комментарии из HTML, JS или CSS кода.
    В зависимости от compact_mode, либо максимально сжимает (сохраняя синтаксис), либо оставляет отступы.
    """
    # Remove multi-line comments first
    cleaned_content_str = re.sub(r'', '', content) # HTML
    cleaned_content_str = re.sub(r'/\*[\s\S]*?\*/', '', cleaned_content_str) # JS/CSS

    processed_lines = []
    for line in cleaned_content_str.splitlines():
        original_line_stripped = line.strip()

        if original_line_stripped.startswith('//'):
            continue

        match = re.search(r'//', line)
        if match:
            pre_comment_part = line[:match.start()]
            single_quotes_odd = (pre_comment_part.count("'") - pre_comment_part.count("\\'")) % 2 == 1
            double_quotes_odd = (pre_comment_part.count('"') - pre_comment_part.count('\\"')) % 2 == 1
            
            if single_quotes_odd or double_quotes_odd:
                processed_lines.append(line)
            else:
                processed_lines.append(line[:match.start()].rstrip())
        else:
            processed_lines.append(line)
    
    cleaned_content_str = "\n".join(processed_lines)

    # Final cleanup based on mode
    if compact_mode:
        # **REVISED COMPACT MODE FOR HTML/CSS/JS**
        # Replace multiple whitespace chars with a single space.
        # This preserves essential spaces for syntax (e.g., between HTML attributes, CSS properties).
        cleaned_content_str = re.sub(r'\s+', ' ', cleaned_content_str).strip()
        
        # Optionally remove spaces around common delimiters if safe (can be tricky, re-evaluate if issues arise)
        # For CSS/JS, this is generally safe:
        cleaned_content_str = re.sub(r'\s*([{};:,])\s*', r'\1', cleaned_content_str)
        # Special case for HTML tags: Remove spaces around < and >
        cleaned_content_str = re.sub(r'\s*(<)\s*', r'\1', cleaned_content_str)
        cleaned_content_str = re.sub(r'\s*(>)\s*', r'\1', cleaned_content_str)
        # Remove semicolons from CSS/JS if followed by a closing brace or end of line (this is still risky for JS)
        # Let's be safer and KEEP semicolons unless you have a dedicated JS minifier
        # For CSS, can remove if not followed by another declaration:
        cleaned_content_str = re.sub(r';}', '}', cleaned_content_str) # Remove ; before } in CSS
        cleaned_content_str = re.sub(r';\s*\n', '\n', cleaned_content_str) # Remove ; followed by newline

    else: # Readable mode
        cleaned_content_str = re.sub(r'\n{3,}', '\n\n', cleaned_content_str)
        cleaned_content_str = re.sub(r'[ \t]+$', '', cleaned_content_str, flags=re.MULTILINE)
        cleaned_content_str = cleaned_content_str.strip()
        
    return cleaned_content_str


# --- Основная логика обработки файлов ---

def process_file(filepath, backup_dir, compact_mode):
    """
    Обрабатывает один файл: удаляет комментарии и делает бэкап.
    """
    filename, file_extension = os.path.splitext(filepath)
    file_extension = file_extension.lower()

    supported_extensions = ['.py', '.html', '.js', '.css']
    if file_extension not in supported_extensions:
        return 

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()

        cleaned_content = original_content

        if file_extension == '.py':
            cleaned_content = _clean_python_code(original_content, compact_mode)
        elif file_extension in ['.html', '.js', '.css']:
            cleaned_content = _clean_html_js_css_code(original_content, compact_mode)
        
        if cleaned_content != original_content:
            # Create backup
            script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            relative_path = os.path.relpath(filepath, start=script_dir)
            backup_filepath = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(backup_filepath), exist_ok=True)
            shutil.copy2(filepath, backup_filepath)
            print(f"Бэкап создан: {backup_filepath}")

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
            print(f"Очищено: {filepath} (Режим: {'Плотный' if compact_mode else 'Читаемый'})")
        # else:
        #     print(f"В файле '{filepath}' не найдено комментариев или изменений.")

    except Exception as e:
        print(f"Ошибка при обработке '{filepath}': {e}")


def main():
    current_directory = os.path.dirname(os.path.abspath(sys.argv[0]))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder_name = f"backup_cleaned_files_{timestamp}"
    backup_dir = os.path.join(current_directory, backup_folder_name)
    
    os.makedirs(backup_dir, exist_ok=True)
    print(f"Файлы будут бэкапированы в: {backup_dir}")

    print("\nВыберите режим очистки:")
    print("1. Читаемый (Readable): Сохраняет отступы и разумные пустые строки для удобства чтения человеком (рекомендуется для проектов).")
    print("2. Плотный (Compact): Максимально сжимает код, сохраняя синтаксическую корректность (удобно для нейросетей).")
    
    mode_choice = input("Введите 1 или 2: ").strip()
    
    compact_mode = False
    if mode_choice == '2':
        compact_mode = True
        print("Выбран плотный режим.")
    elif mode_choice == '1':
        print("Выбран читаемый режим.")
    else:
        print("Неверный выбор. По умолчанию будет использоваться читаемый режим.")

    print(f"\nНачинаем очистку от комментариев в: {current_directory} и всех подпапках...")

    ignored_dirs = ['venv', '.venv']

    for root, dirs, files in os.walk(current_directory):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]

        for file in files:
            filepath = os.path.join(root, file)
            if os.path.abspath(filepath) == os.path.abspath(sys.argv[0]) or filepath.startswith(backup_dir):
                continue
            
            process_file(filepath, backup_dir, compact_mode)
    
    print("\nОчистка завершена!")
    print(f"Резервные копии всех измененных файлов находятся в папке: {backup_dir}")

if __name__ == "__main__":
    print("--- ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ ---")
    print("Этот скрипт изменяет файлы напрямую.")
    print("Автоматически будут созданы резервные копии измененных файлов в новой папке.")
    print("Всегда рекомендуется иметь дополнительные резервные копии ваших проектов!")
    input("Нажмите Enter, чтобы продолжить, или закройте окно, чтобы отменить...")

    main()