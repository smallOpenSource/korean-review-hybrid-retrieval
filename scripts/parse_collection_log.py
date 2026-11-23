import re
import ast
import sys

def parse_log_and_print_table(log_path):
    try:
        with open(log_path, 'r') as f:
            content = f.read()
            
        # Find the final results dictionary
        # It usually starts with something like "{'status': 'completed', 'apps_processed':" 
        # or contains "app_results"
        # Based on previous output, it seems the job returns a dict which might be printed to stdout/log
        
        # Let's look for the specific pattern of the results dictionary
        # The log showed: ... 'com.example.card_i': {'package_id': ...
        # This suggests the dictionary is printed.
        
        # Strategy: Find the last occurrence of a large dictionary-like string
        # Or better, look for the "Review collection completed:" log line which summarizes, 
        # but the user wants the FULL list.
        
        # The log output in the previous turn showed the dictionary being printed at the very end.
        # It looks like a python dict string.
        
        # Let's try to find the dictionary that contains 'app_results' or keys that look like package ids.
        # Since the log might contain many things, let's try to extract the dictionary from the end of the file.
        
        # We'll search for the start of the app_results dictionary or the individual app result lines.
        # Actually, the log showed the return value of the job being printed:
        # "{'status': 'completed', ... 'app_results': { ... }}"
        
        # Let's try to parse the last line if it's the dict, or search for it.
        
        # Alternative: Parse "Collected X reviews for Y" lines if the dict is hard to parse.
        # But the dict has the exact numbers for new/duplicate.
        
        # The log ends with a large dictionary. Let's try to find the last occurrence of "app_results"
        # and extract the dictionary from there.
        
        # Find the start of the results dictionary
        start_marker = "'app_results': {"
        start_idx = content.rfind(start_marker)
        
        if start_idx == -1:
            print("Could not find 'app_results' in log.")
            return
            
        # Extract from start_marker to the end, but we need to be careful about the closing brace.
        # The log ends with "}, 'duration_seconds': ...}"
        # So app_results value ends before 'duration_seconds'
        
        # Let's extract the string starting from the brace after 'app_results': 
        dict_start = start_idx + len("'app_results': ")
        
        # We can try to use ast.literal_eval on the whole last line if it's a valid python dict representation
        # The log tail shows the last line IS the dict.
        lines = content.strip().split('\n')
        last_line = lines[-1]
        
        if "'app_results':" in last_line:
            try:
                # It might be truncated in the file if the buffer wasn't flushed, but let's hope not.
                # The tail output showed it ending with duration_seconds, so it seems complete.
                data = ast.literal_eval(last_line)
                app_results = data.get('app_results', {})
            except Exception as e:
                print(f"Direct eval failed: {e}. Trying regex fallback.")
                # Fallback to regex if eval fails (e.g. due to some non-python syntax or truncation)
                pattern = r"'(?P<pkg>[\w\.]+)'\s*:\s*\{'package_id':\s*'(?P<pkg_id>[\w\.]+)',\s*'app_name':\s*'(?P<name>[^']+)',\s*'total':\s*(?P<total>\d+),\s*'new':\s*(?P<new>\d+),\s*'duplicate':\s*(?P<dup>\d+)"
                matches = re.finditer(pattern, last_line)
                app_results = {}
                for m in matches:
                    app_results[m.group('pkg')] = {
                        'app_name': m.group('name'),
                        'total': int(m.group('total')),
                        'new': int(m.group('new')),
                        'duplicate': int(m.group('dup'))
                    }
        else:
             # Fallback to regex on the whole content if last line isn't it
            pattern = r"'(?P<pkg>[\w\.]+)'\s*:\s*\{'package_id':\s*'(?P<pkg_id>[\w\.]+)',\s*'app_name':\s*'(?P<name>[^']+)',\s*'total':\s*(?P<total>\d+),\s*'new':\s*(?P<new>\d+),\s*'duplicate':\s*(?P<dup>\d+)"
            matches = re.finditer(pattern, content)
            app_results = {}
            for m in matches:
                # Update dict to keep latest if multiple
                app_results[m.group('pkg')] = {
                    'app_name': m.group('name'),
                    'total': int(m.group('total')),
                    'new': int(m.group('new')),
                    'duplicate': int(m.group('dup'))
                }
                
        if not app_results:
            print("No app results found in log.")
            return

        # Sort by New count descending
        sorted_results = sorted(app_results.values(), key=lambda x: x['new'], reverse=True)
        
        print(f"### 📊 전체 수집 결과 리포트")
        print(f"총 {len(sorted_results)}개 앱 데이터 수집 완료\n")
        
        print(f"| 앱 이름 | 패키지 ID | 신규 수집 (New) | 중복 (Dup) | 총 확인 (Total) |")
        print(f"|---|---|---|---|---|")
        
        total_new = 0
        total_dup = 0
        total_checked = 0
        
        for res in sorted_results:
            name = res['app_name']
            pkg = res.get('package_id', 'N/A')
            new = res['new']
            dup = res['duplicate']
            total = res['total']
            
            total_new += new
            total_dup += dup
            total_checked += total
            
            # Highlight rows with new data
            if new > 0:
                print(f"| **{name}** | `{pkg}` | **{new:,}** | {dup:,} | {total:,} |")
            else:
                print(f"| {name} | `{pkg}` | {new:,} | {dup:,} | {total:,} |")
                
        print(f"| **합계** | - | **{total_new:,}** | **{total_dup:,}** | **{total_checked:,}** |")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    parse_log_and_print_table('/tmp/collect_gap.log')
