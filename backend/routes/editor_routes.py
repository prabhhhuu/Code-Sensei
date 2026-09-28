from functools import wraps
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from database import get_db
import datetime
from ai_service import get_ai_response

editor_bp = Blueprint("editor", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json:
                return jsonify({"error": "Please log in to continue."}), 401
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def detect_difficulty(code, language):
    """Auto-detect difficulty from code length and complexity."""
    lines = [l for l in code.split('\n') if l.strip()]
    length = len(lines)
    # Simple heuristics
    complex_keywords = ['class ', 'async ', 'thread', 'recursive', 'algorithm',
                        'dynamic', 'interface ', 'abstract ', 'template', 'inherit']
    has_complex = any(kw in code.lower() for kw in complex_keywords)

    if length <= 15 and not has_complex:
        return 'beginner'
    elif length <= 40 or not has_complex:
        return 'medium'
    else:
        return 'advanced'


def calculate_streaks(uid, db):
    """Calculate current and longest submission streaks."""
    rows = db.execute(
        "SELECT DISTINCT date(created_at) as day FROM code_history "
        "WHERE user_id = ? ORDER BY day DESC",
        (uid,)
    ).fetchall()

    if not rows:
        return 0, 0

    days = [datetime.date.fromisoformat(r["day"]) for r in rows]
    today = datetime.date.today()

    # Current streak
    current = 0
    check = today
    for day in days:
        if day == check or day == check - datetime.timedelta(days=1):
            current += 1
            check = day
        else:
            break

    # Longest streak
    longest = 1
    streak  = 1
    for i in range(1, len(days)):
        if (days[i-1] - days[i]).days == 1:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 1

    return current, longest


# ── Routes ────────────────────────────────────────────────────────────────────

@editor_bp.route("/")
@editor_bp.route("/editor")
@login_required
def index():
    return render_template("editor.html")


@editor_bp.route("/api/analyse", methods=["POST"])
@login_required
def analyse():
    data     = request.get_json()
    code     = data.get("code", "").strip()
    language = data.get("language", "python")
    mode     = data.get("mode", "explain")
    model    = data.get("model", "gpt-oss-120b")

    if not code:
        return jsonify({"error": "No code provided"}), 400

    result     = get_ai_response(code, language, mode, model)
    difficulty = detect_difficulty(code, language)

    try:
        db = get_db()
        db.execute(
            "INSERT INTO code_history (user_id, code, language, mode, result, difficulty, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session["user_id"], code, language, mode, result,
             difficulty, datetime.datetime.now().isoformat())
        )
        db.commit()
    except Exception as e:
        print(f"Error saving to history: {e}")

    return jsonify({"result": result})


@editor_bp.route("/history")
@login_required
def history():
    rows = get_db().execute(
        "SELECT * FROM code_history WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    return render_template("history.html", history=rows)


@editor_bp.route("/dashboard")
@login_required
def dashboard():
    db  = get_db()
    uid = session["user_id"]

    total = db.execute(
        "SELECT COUNT(*) AS c FROM code_history WHERE user_id = ?", (uid,)
    ).fetchone()["c"]

    lang_rows = db.execute(
        "SELECT language, COUNT(*) AS count FROM code_history "
        "WHERE user_id = ? GROUP BY language ORDER BY count DESC", (uid,)
    ).fetchall()

    diff_rows = db.execute(
        "SELECT difficulty, COUNT(*) AS count FROM code_history "
        "WHERE user_id = ? AND difficulty IS NOT NULL GROUP BY difficulty", (uid,)
    ).fetchall()

    mode_rows = db.execute(
        "SELECT mode, COUNT(*) AS count FROM code_history "
        "WHERE user_id = ? GROUP BY mode ORDER BY count DESC", (uid,)
    ).fetchall()

    history = db.execute(
        "SELECT * FROM code_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (uid,)
    ).fetchall()

    current_streak, longest_streak = calculate_streaks(uid, db)

    stats = {
        "total_submissions": total,
        "current_streak":    current_streak,
        "longest_streak":    longest_streak,
        "languages_used":    [r["language"] for r in lang_rows],
    }

    # Challenge stats for dashboard
    ch_attempts = get_db().execute(
        "SELECT * FROM challenge_attempts WHERE user_id=? ORDER BY created_at DESC",
        (uid,)
    ).fetchall()
    ch_total  = len(ch_attempts)
    ch_solved = get_db().execute(
        "SELECT COUNT(DISTINCT challenge_id) AS c FROM challenge_attempts WHERE user_id=? AND passed=1", (uid,)
    ).fetchone()["c"]
    ch_recent = list(ch_attempts[:6])

    return render_template(
        "dashboard.html",
        stats=stats,
        language_stats=[dict(r) for r in lang_rows],
        difficulty_stats=[dict(r) for r in diff_rows],
        mode_stats=[dict(r) for r in mode_rows],
        history=history,
        ch_total=ch_total,
        ch_solved=ch_solved,
        ch_recent=ch_recent,
        challenges_total=len(CHALLENGES),
    )


@editor_bp.route("/shared")
@login_required
def shared():
    return render_template("shared.html")


@editor_bp.route("/api/history/<int:entry_id>", methods=["DELETE"])
@login_required
def delete_history(entry_id):
    try:
        db  = get_db()
        uid = session["user_id"]
        row = db.execute(
            "SELECT id FROM code_history WHERE id = ? AND user_id = ?", (entry_id, uid)
        ).fetchone()
        if not row:
            return jsonify({"success": False, "error": "Not found"}), 404
        db.execute("DELETE FROM code_history WHERE id = ? AND user_id = ?", (entry_id, uid))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Coding Challenges ─────────────────────────────────────────────────────────


CHALLENGES = [

    # ══════════════════ 1. ARRAYS ══════════════════

    {
        "id": 1, "title": "Contains Duplicate", "difficulty": "easy",
        "category": "Arrays", "tags": ["array", "hashset"],
        "description": "Given an integer array `nums`, return `true` if any value appears at least twice, and `false` if every element is distinct.",
        "examples": [
            {"input": "nums = [1,2,3,1]", "output": "true",  "explanation": "1 appears at index 0 and 3"},
            {"input": "nums = [1,2,3,4]", "output": "false", "explanation": "All elements distinct"},
        ],
        "starters": {
            "python":     "def contains_duplicate(nums):\n    # Write your solution here\n    pass\n",
            "javascript": "function containsDuplicate(nums) {\n    // Write your solution here\n}\n",
            "java":       "    public static boolean containsDuplicate(int[] nums) {\n        // Write your solution here\n        return false;\n    }\n",
            "c":          "// Hint: sort or use a manual check\nbool containsDuplicate(int* nums, int n) {\n    // Write your solution here\n    return false;\n}\n",
            "cpp":        "bool containsDuplicate(vector<int>& nums) {\n    // Write your solution here\n    return false;\n}\n",
            "typescript": "function containsDuplicate(nums: number[]): boolean {\n    // Write your solution here\n    return false;\n}\n",
        },
        "tests": [
            {"fn": "contains_duplicate([1,2,3,1])",              "fn_js": "containsDuplicate([1,2,3,1])",              "fn_java": "containsDuplicate(new int[]{1,2,3,1})",              "fn_c": "containsDuplicate((int[]){1,2,3,1}, 4)", "fn_cpp": "([&](){ vector<int> v={1,2,3,1}; return containsDuplicate(v); })()", "expected": True,  "expected_str": "true"},
            {"fn": "contains_duplicate([1,2,3,4])",              "fn_js": "containsDuplicate([1,2,3,4])",              "fn_java": "containsDuplicate(new int[]{1,2,3,4})",              "fn_c": "containsDuplicate((int[]){1,2,3,4}, 4)", "fn_cpp": "([&](){ vector<int> v={1,2,3,4}; return containsDuplicate(v); })()", "expected": False, "expected_str": "false"},
            {"fn": "contains_duplicate([1,1,1,3,3,4,3,2,4,2])", "fn_js": "containsDuplicate([1,1,1,3,3,4,3,2,4,2])", "fn_java": "containsDuplicate(new int[]{1,1,1,3,3,4,3,2,4,2})", "fn_c": "containsDuplicate((int[]){1,1,1,3,3,4,3,2,4,2}, 10)", "fn_cpp": "([&](){ vector<int> v={1,1,1,3,3,4,3,2,4,2}; return containsDuplicate(v); })()", "expected": True,  "expected_str": "true"},
            {"fn": "contains_duplicate([])",                     "fn_js": "containsDuplicate([])",                     "fn_java": "containsDuplicate(new int[]{})",                     "fn_c": "containsDuplicate(NULL, 0)",              "fn_cpp": "([&](){ vector<int> v={}; return containsDuplicate(v); })()", "expected": False, "expected_str": "false"},
        ],
    },
    {
        "id": 2, "title": "Two Sum", "difficulty": "medium",
        "category": "Arrays", "tags": ["array", "hashmap"],
        "description": "Given an array of integers `nums` and an integer `target`, return the **indices** of the two numbers that add up to `target`.\n\nExactly one solution exists. You may not use the same element twice.",
        "examples": [
            {"input": "nums = [2,7,11,15], target = 9", "output": "[0, 1]", "explanation": "nums[0] + nums[1] = 9"},
            {"input": "nums = [3,2,4], target = 6",     "output": "[1, 2]", "explanation": "nums[1] + nums[2] = 6"},
        ],
        "starters": {
            "python":     "def two_sum(nums, target):\n    # Write your solution here\n    pass\n",
            "javascript": "function twoSum(nums, target) {\n    // Write your solution here\n    return [];\n}\n",
            "java":       "    public static int[] twoSum(int[] nums, int target) {\n        // Write your solution here\n        return new int[]{};\n    }\n",
            "c":          "#include <stdlib.h>\nint* twoSum(int* nums, int n, int target, int* returnSize) {\n    *returnSize = 2;\n    int* result = (int*)malloc(2 * sizeof(int));\n    // Write your solution here\n    return result;\n}\n",
            "cpp":        "vector<int> twoSum(vector<int>& nums, int target) {\n    // Write your solution here\n    return {};\n}\n",
            "typescript": "function twoSum(nums: number[], target: number): number[] {\n    // Write your solution here\n    return [];\n}\n",
        },
        "tests": [
            {"fn": "two_sum([2,7,11,15], 9)", "fn_js": "JSON.stringify(twoSum([2,7,11,15], 9))", "fn_java": "java.util.Arrays.toString(twoSum(new int[]{2,7,11,15}, 9))", "fn_cpp": "([&](){ vector<int> v={2,7,11,15}; auto r=twoSum(v,9); return to_string(r[0])+\",\"+to_string(r[1]); })()", "expected": [0,1], "expected_str": "[0,1]"},
            {"fn": "two_sum([3,2,4], 6)",     "fn_js": "JSON.stringify(twoSum([3,2,4], 6))",     "fn_java": "java.util.Arrays.toString(twoSum(new int[]{3,2,4}, 6))",     "fn_cpp": "([&](){ vector<int> v={3,2,4}; auto r=twoSum(v,6); return to_string(r[0])+\",\"+to_string(r[1]); })()",   "expected": [1,2], "expected_str": "[1,2]"},
            {"fn": "two_sum([3,3], 6)",        "fn_js": "JSON.stringify(twoSum([3,3], 6))",        "fn_java": "java.util.Arrays.toString(twoSum(new int[]{3,3}, 6))",        "fn_cpp": "([&](){ vector<int> v={3,3}; auto r=twoSum(v,6); return to_string(r[0])+\",\"+to_string(r[1]); })()",     "expected": [0,1], "expected_str": "[0,1]"},
            {"fn": "two_sum([1,5,3,2], 4)",    "fn_js": "JSON.stringify(twoSum([1,5,3,2], 4))",    "fn_java": "java.util.Arrays.toString(twoSum(new int[]{1,5,3,2}, 4))",    "fn_cpp": "([&](){ vector<int> v={1,5,3,2}; auto r=twoSum(v,4); return to_string(r[0])+\",\"+to_string(r[1]); })()", "expected": [0,2], "expected_str": "[0,2]"},
        ],
    },
    {
        "id": 3, "title": "Maximum Subarray", "difficulty": "hard",
        "category": "Arrays", "tags": ["array", "dynamic programming", "kadane"],
        "description": "Given an integer array `nums`, find the **contiguous subarray** with the largest sum and return its sum.\n\nA subarray must contain at least one element.\n\n**Hint:** Kadane's Algorithm — O(n) time, O(1) space.",
        "examples": [
            {"input": "nums = [-2,1,-3,4,-1,2,1,-5,4]", "output": "6",  "explanation": "[4,-1,2,1] has sum 6"},
            {"input": "nums = [5,4,-1,7,8]",              "output": "23", "explanation": "Whole array"},
        ],
        "starters": {
            "python":     "def max_subarray(nums):\n    # Write your solution here\n    pass\n",
            "javascript": "function maxSubArray(nums) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int maxSubArray(int[] nums) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int maxSubArray(int* nums, int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int maxSubArray(vector<int>& nums) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function maxSubArray(nums: number[]): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "max_subarray([-2,1,-3,4,-1,2,1,-5,4])", "fn_js": "maxSubArray([-2,1,-3,4,-1,2,1,-5,4])", "fn_java": "maxSubArray(new int[]{-2,1,-3,4,-1,2,1,-5,4})", "fn_c": "maxSubArray((int[]){-2,1,-3,4,-1,2,1,-5,4},9)", "fn_cpp": "([&](){ vector<int> v={-2,1,-3,4,-1,2,1,-5,4}; return maxSubArray(v); })()", "expected": 6},
            {"fn": "max_subarray([1])",                       "fn_js": "maxSubArray([1])",                       "fn_java": "maxSubArray(new int[]{1})",                       "fn_c": "maxSubArray((int[]){1},1)",                "fn_cpp": "([&](){ vector<int> v={1}; return maxSubArray(v); })()",                       "expected": 1},
            {"fn": "max_subarray([5,4,-1,7,8])",              "fn_js": "maxSubArray([5,4,-1,7,8])",              "fn_java": "maxSubArray(new int[]{5,4,-1,7,8})",              "fn_c": "maxSubArray((int[]){5,4,-1,7,8},5)",      "fn_cpp": "([&](){ vector<int> v={5,4,-1,7,8}; return maxSubArray(v); })()",              "expected": 23},
            {"fn": "max_subarray([-1,-2,-3])",                "fn_js": "maxSubArray([-1,-2,-3])",                "fn_java": "maxSubArray(new int[]{-1,-2,-3})",                "fn_c": "maxSubArray((int[]){-1,-2,-3},3)",        "fn_cpp": "([&](){ vector<int> v={-1,-2,-3}; return maxSubArray(v); })()",                "expected": -1},
        ],
    },

    # ══════════════════ 2. STRINGS ══════════════════

    {
        "id": 4, "title": "Reverse a String", "difficulty": "easy",
        "category": "Strings", "tags": ["string", "iteration"],
        "description": "Write a function that takes a string `s` and returns it reversed.\n\n**Constraint:** Do not use built-in reverse methods. Use a loop.",
        "examples": [
            {"input": 's = "hello"', "output": '"olleh"', "explanation": "Characters reversed"},
            {"input": 's = "abcd"',  "output": '"dcba"',  "explanation": ""},
        ],
        "starters": {
            "python":     "def reverse_string(s):\n    # Write your solution here\n    pass\n",
            "javascript": "function reverseString(s) {\n    // Write your solution here\n    return '';\n}\n",
            "java":       "    public static String reverseString(String s) {\n        // Write your solution here\n        return \"\";\n    }\n",
            "c":          "#include <string.h>\nchar* reverseString(char* s) {\n    int n = strlen(s);\n    for (int i = 0; i < n/2; i++) {\n        char t = s[i]; s[i] = s[n-1-i]; s[n-1-i] = t;\n    }\n    return s;\n}\n",
            "cpp":        "string reverseString(string s) {\n    // Write your solution here\n    return \"\";\n}\n",
            "typescript": "function reverseString(s: string): string {\n    // Write your solution here\n    return '';\n}\n",
        },
        "tests": [
            {"fn": "reverse_string('hello')",  "fn_js": "reverseString('hello')",  "fn_java": "reverseString(\"hello\")",  "fn_cpp": "reverseString(\"hello\")", "expected": "olleh"},
            {"fn": "reverse_string('python')", "fn_js": "reverseString('python')", "fn_java": "reverseString(\"python\")", "fn_cpp": "reverseString(\"python\")", "expected": "nohtyp"},
            {"fn": "reverse_string('a')",      "fn_js": "reverseString('a')",      "fn_java": "reverseString(\"a\")",      "fn_cpp": "reverseString(\"a\")",      "expected": "a"},
            {"fn": "reverse_string('abcd')",   "fn_js": "reverseString('abcd')",   "fn_java": "reverseString(\"abcd\")",   "fn_cpp": "reverseString(\"abcd\")",   "expected": "dcba"},
        ],
    },
    {
        "id": 5, "title": "Valid Palindrome", "difficulty": "medium",
        "category": "Strings", "tags": ["string", "two-pointer"],
        "description": "A phrase is a palindrome if, after converting all letters to lowercase and removing all non-alphanumeric characters, it reads the same forward and backward.\n\nReturn `true` if `s` is a palindrome, otherwise `false`.",
        "examples": [
            {"input": 's = "A man, a plan, a canal: Panama"', "output": "true",  "explanation": "Becomes 'amanaplanacanalpanama'"},
            {"input": 's = "race a car"',                      "output": "false", "explanation": "Becomes 'raceacar'"},
        ],
        "starters": {
            "python":     "def is_palindrome(s):\n    # Write your solution here\n    pass\n",
            "javascript": "function isPalindrome(s) {\n    // Write your solution here\n    return false;\n}\n",
            "java":       "    public static boolean isPalindrome(String s) {\n        // Write your solution here\n        return false;\n    }\n",
            "c":          "#include <ctype.h>\nbool isPalindrome(char* s) {\n    // Write your solution here\n    return false;\n}\n",
            "cpp":        "bool isPalindrome(string s) {\n    // Write your solution here\n    return false;\n}\n",
            "typescript": "function isPalindrome(s: string): boolean {\n    // Write your solution here\n    return false;\n}\n",
        },
        "tests": [
            {"fn": "is_palindrome('A man, a plan, a canal: Panama')", "fn_js": "isPalindrome('A man, a plan, a canal: Panama')", "fn_java": "isPalindrome(\"A man, a plan, a canal: Panama\")", "fn_cpp": "isPalindrome(\"A man, a plan, a canal: Panama\")", "expected": True,  "expected_str": "true"},
            {"fn": "is_palindrome('race a car')",                      "fn_js": "isPalindrome('race a car')",                      "fn_java": "isPalindrome(\"race a car\")",                      "fn_cpp": "isPalindrome(\"race a car\")",                      "expected": False, "expected_str": "false"},
            {"fn": "is_palindrome(' ')",                               "fn_js": "isPalindrome(' ')",                               "fn_java": "isPalindrome(\" \")",                               "fn_cpp": "isPalindrome(\" \")",                               "expected": True,  "expected_str": "true"},
            {"fn": "is_palindrome('racecar')",                         "fn_js": "isPalindrome('racecar')",                         "fn_java": "isPalindrome(\"racecar\")",                         "fn_cpp": "isPalindrome(\"racecar\")",                         "expected": True,  "expected_str": "true"},
        ],
    },
    {
        "id": 6, "title": "Longest Substring Without Repeating Characters", "difficulty": "hard",
        "category": "Strings", "tags": ["string", "sliding window", "hashset"],
        "description": "Given a string `s`, find the **length** of the longest substring without repeating characters.\n\n**Hint:** Sliding window with a set — O(n) time.",
        "examples": [
            {"input": 's = "abcabcbb"', "output": "3", "explanation": "'abc' has length 3"},
            {"input": 's = "bbbbb"',    "output": "1", "explanation": "'b'"},
            {"input": 's = "pwwkew"',   "output": "3", "explanation": "'wke'"},
        ],
        "starters": {
            "python":     "def length_of_longest_substring(s):\n    # Write your solution here\n    pass\n",
            "javascript": "function lengthOfLongestSubstring(s) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int lengthOfLongestSubstring(String s) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int lengthOfLongestSubstring(char* s) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int lengthOfLongestSubstring(string s) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function lengthOfLongestSubstring(s: string): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "length_of_longest_substring('abcabcbb')", "fn_js": "lengthOfLongestSubstring('abcabcbb')", "fn_java": "lengthOfLongestSubstring(\"abcabcbb\")", "fn_cpp": "lengthOfLongestSubstring(\"abcabcbb\")", "expected": 3},
            {"fn": "length_of_longest_substring('bbbbb')",    "fn_js": "lengthOfLongestSubstring('bbbbb')",    "fn_java": "lengthOfLongestSubstring(\"bbbbb\")",    "fn_cpp": "lengthOfLongestSubstring(\"bbbbb\")",    "expected": 1},
            {"fn": "length_of_longest_substring('pwwkew')",   "fn_js": "lengthOfLongestSubstring('pwwkew')",   "fn_java": "lengthOfLongestSubstring(\"pwwkew\")",   "fn_cpp": "lengthOfLongestSubstring(\"pwwkew\")",   "expected": 3},
            {"fn": "length_of_longest_substring('')",         "fn_js": "lengthOfLongestSubstring('')",         "fn_java": "lengthOfLongestSubstring(\"\")",         "fn_cpp": "lengthOfLongestSubstring(\"\")",         "expected": 0},
            {"fn": "length_of_longest_substring('au')",       "fn_js": "lengthOfLongestSubstring('au')",       "fn_java": "lengthOfLongestSubstring(\"au\")",       "fn_cpp": "lengthOfLongestSubstring(\"au\")",       "expected": 2},
        ],
    },

    # ══════════════════ 3. MATH ══════════════════

    {
        "id": 7, "title": "FizzBuzz", "difficulty": "easy",
        "category": "Math", "tags": ["math", "string", "modulo"],
        "description": "Given an integer `n`, return a list of strings for numbers 1 to n:\n- `\"FizzBuzz\"` for multiples of both 3 and 5\n- `\"Fizz\"` for multiples of 3\n- `\"Buzz\"` for multiples of 5\n- The number as a string otherwise",
        "examples": [
            {"input": "n = 5",  "output": '["1","2","Fizz","4","Buzz"]', "explanation": ""},
            {"input": "n = 15", "output": '["1",...,"FizzBuzz"]',        "explanation": "15 is a multiple of both"},
        ],
        "starters": {
            "python":     "def fizz_buzz(n):\n    # Write your solution here\n    pass\n",
            "javascript": "function fizzBuzz(n) {\n    const result = [];\n    // Write your solution here\n    return result;\n}\n",
            "java":       "    public static java.util.List<String> fizzBuzz(int n) {\n        java.util.List<String> result = new java.util.ArrayList<>();\n        // Write your solution here\n        return result;\n    }\n",
            "c":          "// Return array via out-param\nvoid fizzBuzz(int n, char result[][9]) {\n    for (int i = 1; i <= n; i++) {\n        // Write your solution here\n    }\n}\n",
            "cpp":        "vector<string> fizzBuzz(int n) {\n    vector<string> result;\n    // Write your solution here\n    return result;\n}\n",
            "typescript": "function fizzBuzz(n: number): string[] {\n    const result: string[] = [];\n    // Write your solution here\n    return result;\n}\n",
        },
        "tests": [
            {"fn": "fizz_buzz(3)",  "fn_js": "JSON.stringify(fizzBuzz(3))",  "fn_java": "fizzBuzz(3).toString()",  "fn_cpp": "([&](){ auto v=fizzBuzz(3); string s=\"[\"; for(auto& x:v) s+=\"\\\"\"+x+\"\\\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()", "expected": ["1","2","Fizz"]},
            {"fn": "fizz_buzz(5)",  "fn_js": "JSON.stringify(fizzBuzz(5))",  "fn_java": "fizzBuzz(5).toString()",  "fn_cpp": "([&](){ auto v=fizzBuzz(5); string s=\"[\"; for(auto& x:v) s+=\"\\\"\"+x+\"\\\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()", "expected": ["1","2","Fizz","4","Buzz"]},
            {"fn": "fizz_buzz(1)",  "fn_js": "JSON.stringify(fizzBuzz(1))",  "fn_java": "fizzBuzz(1).toString()",  "fn_cpp": "([&](){ auto v=fizzBuzz(1); return v[0]; })()",  "expected": ["1"]},
        ],
    },
    {
        "id": 8, "title": "Count Primes", "difficulty": "medium",
        "category": "Math", "tags": ["math", "sieve"],
        "description": "Given an integer `n`, return the **count** of prime numbers less than `n`.\n\n**Hint:** Use the Sieve of Eratosthenes for O(n log log n) time.",
        "examples": [
            {"input": "n = 10", "output": "4", "explanation": "Primes < 10: 2, 3, 5, 7"},
            {"input": "n = 0",  "output": "0", "explanation": "No primes < 0"},
        ],
        "starters": {
            "python":     "def count_primes(n):\n    # Write your solution here\n    pass\n",
            "javascript": "function countPrimes(n) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int countPrimes(int n) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int countPrimes(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int countPrimes(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function countPrimes(n: number): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "count_primes(10)", "fn_js": "countPrimes(10)", "fn_java": "countPrimes(10)", "fn_c": "countPrimes(10)", "fn_cpp": "countPrimes(10)", "expected": 4},
            {"fn": "count_primes(0)",  "fn_js": "countPrimes(0)",  "fn_java": "countPrimes(0)",  "fn_c": "countPrimes(0)",  "fn_cpp": "countPrimes(0)",  "expected": 0},
            {"fn": "count_primes(1)",  "fn_js": "countPrimes(1)",  "fn_java": "countPrimes(1)",  "fn_c": "countPrimes(1)",  "fn_cpp": "countPrimes(1)",  "expected": 0},
            {"fn": "count_primes(20)", "fn_js": "countPrimes(20)", "fn_java": "countPrimes(20)", "fn_c": "countPrimes(20)", "fn_cpp": "countPrimes(20)", "expected": 8},
        ],
    },
    {
        "id": 9, "title": "Climbing Stairs", "difficulty": "hard",
        "category": "Math", "tags": ["dynamic programming", "fibonacci", "math"],
        "description": "You are climbing a staircase with `n` steps. Each time you can climb **1 or 2** steps.\n\nIn how many distinct ways can you climb to the top?\n\n**Hint:** This is the Fibonacci pattern.",
        "examples": [
            {"input": "n = 2", "output": "2", "explanation": "1+1 or 2"},
            {"input": "n = 3", "output": "3", "explanation": "1+1+1, 1+2, 2+1"},
        ],
        "starters": {
            "python":     "def climb_stairs(n):\n    # Write your solution here\n    pass\n",
            "javascript": "function climbStairs(n) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int climbStairs(int n) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int climbStairs(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int climbStairs(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function climbStairs(n: number): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "climb_stairs(1)",  "fn_js": "climbStairs(1)",  "fn_java": "climbStairs(1)",  "fn_c": "climbStairs(1)",  "fn_cpp": "climbStairs(1)",  "expected": 1},
            {"fn": "climb_stairs(2)",  "fn_js": "climbStairs(2)",  "fn_java": "climbStairs(2)",  "fn_c": "climbStairs(2)",  "fn_cpp": "climbStairs(2)",  "expected": 2},
            {"fn": "climb_stairs(3)",  "fn_js": "climbStairs(3)",  "fn_java": "climbStairs(3)",  "fn_c": "climbStairs(3)",  "fn_cpp": "climbStairs(3)",  "expected": 3},
            {"fn": "climb_stairs(5)",  "fn_js": "climbStairs(5)",  "fn_java": "climbStairs(5)",  "fn_c": "climbStairs(5)",  "fn_cpp": "climbStairs(5)",  "expected": 8},
            {"fn": "climb_stairs(10)", "fn_js": "climbStairs(10)", "fn_java": "climbStairs(10)", "fn_c": "climbStairs(10)", "fn_cpp": "climbStairs(10)", "expected": 89},
        ],
    },

    # ══════════════════ 4. DYNAMIC PROGRAMMING ══════════════════

    {
        "id": 10, "title": "Fibonacci Number", "difficulty": "easy",
        "category": "Dynamic Programming", "tags": ["dp", "recursion", "memoization"],
        "description": "The Fibonacci sequence: F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2).\n\nGiven `n`, return `F(n)`.\n\n**Bonus:** Try iterative DP to avoid O(n) stack space.",
        "examples": [
            {"input": "n = 0", "output": "0", "explanation": "Base case"},
            {"input": "n = 4", "output": "3", "explanation": "0,1,1,2,3"},
        ],
        "starters": {
            "python":     "def fib(n):\n    # Write your solution here\n    pass\n",
            "javascript": "function fib(n) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int fib(int n) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int fib(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int fib(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function fib(n: number): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "fib(0)",  "fn_js": "fib(0)",  "fn_java": "fib(0)",  "fn_c": "fib(0)",  "fn_cpp": "fib(0)",  "expected": 0},
            {"fn": "fib(1)",  "fn_js": "fib(1)",  "fn_java": "fib(1)",  "fn_c": "fib(1)",  "fn_cpp": "fib(1)",  "expected": 1},
            {"fn": "fib(4)",  "fn_js": "fib(4)",  "fn_java": "fib(4)",  "fn_c": "fib(4)",  "fn_cpp": "fib(4)",  "expected": 3},
            {"fn": "fib(10)", "fn_js": "fib(10)", "fn_java": "fib(10)", "fn_c": "fib(10)", "fn_cpp": "fib(10)", "expected": 55},
            {"fn": "fib(15)", "fn_js": "fib(15)", "fn_java": "fib(15)", "fn_c": "fib(15)", "fn_cpp": "fib(15)", "expected": 610},
        ],
    },
    {
        "id": 11, "title": "House Robber", "difficulty": "medium",
        "category": "Dynamic Programming", "tags": ["dp", "array"],
        "description": "You are a robber. Adjacent houses cannot both be robbed.\n\nGiven `nums` where each element is the amount of money in a house, return the **maximum amount** you can rob.",
        "examples": [
            {"input": "nums = [1,2,3,1]",   "output": "4",  "explanation": "Rob house 1 (1) + house 3 (3) = 4"},
            {"input": "nums = [2,7,9,3,1]", "output": "12", "explanation": "Rob 2+9+1 = 12"},
        ],
        "starters": {
            "python":     "def house_robber(nums):\n    # Write your solution here\n    pass\n",
            "javascript": "function houseRobber(nums) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int houseRobber(int[] nums) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int houseRobber(int* nums, int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int houseRobber(vector<int>& nums) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function houseRobber(nums: number[]): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "house_robber([1,2,3,1])",   "fn_js": "houseRobber([1,2,3,1])",   "fn_java": "houseRobber(new int[]{1,2,3,1})",   "fn_c": "houseRobber((int[]){1,2,3,1},4)",   "fn_cpp": "([&](){ vector<int> v={1,2,3,1};   return houseRobber(v); })()", "expected": 4},
            {"fn": "house_robber([2,7,9,3,1])", "fn_js": "houseRobber([2,7,9,3,1])", "fn_java": "houseRobber(new int[]{2,7,9,3,1})", "fn_c": "houseRobber((int[]){2,7,9,3,1},5)", "fn_cpp": "([&](){ vector<int> v={2,7,9,3,1}; return houseRobber(v); })()", "expected": 12},
            {"fn": "house_robber([1])",          "fn_js": "houseRobber([1])",          "fn_java": "houseRobber(new int[]{1})",          "fn_c": "houseRobber((int[]){1},1)",          "fn_cpp": "([&](){ vector<int> v={1};         return houseRobber(v); })()", "expected": 1},
            {"fn": "house_robber([2,1])",        "fn_js": "houseRobber([2,1])",        "fn_java": "houseRobber(new int[]{2,1})",        "fn_c": "houseRobber((int[]){2,1},2)",        "fn_cpp": "([&](){ vector<int> v={2,1};       return houseRobber(v); })()", "expected": 2},
        ],
    },
    {
        "id": 12, "title": "Coin Change", "difficulty": "hard",
        "category": "Dynamic Programming", "tags": ["dp", "bfs"],
        "description": "Given `coins` denominations and an `amount`, return the **fewest coins** needed to make up `amount`. Return `-1` if impossible.\n\nYou may use each coin an unlimited number of times.",
        "examples": [
            {"input": "coins=[1,5,11], amount=15", "output": "3",  "explanation": "5+5+5"},
            {"input": "coins=[2], amount=3",       "output": "-1", "explanation": "Impossible"},
        ],
        "starters": {
            "python":     "def coin_change(coins, amount):\n    # Write your solution here\n    pass\n",
            "javascript": "function coinChange(coins, amount) {\n    // Write your solution here\n    return -1;\n}\n",
            "java":       "    public static int coinChange(int[] coins, int amount) {\n        // Write your solution here\n        return -1;\n    }\n",
            "c":          "int coinChange(int* coins, int n, int amount) {\n    // Write your solution here\n    return -1;\n}\n",
            "cpp":        "int coinChange(vector<int>& coins, int amount) {\n    // Write your solution here\n    return -1;\n}\n",
            "typescript": "function coinChange(coins: number[], amount: number): number {\n    // Write your solution here\n    return -1;\n}\n",
        },
        "tests": [
            {"fn": "coin_change([1,5,11], 15)", "fn_js": "coinChange([1,5,11], 15)", "fn_java": "coinChange(new int[]{1,5,11}, 15)", "fn_c": "coinChange((int[]){1,5,11},3,15)", "fn_cpp": "([&](){ vector<int> v={1,5,11}; return coinChange(v,15); })()", "expected": 3},
            {"fn": "coin_change([2], 3)",       "fn_js": "coinChange([2], 3)",       "fn_java": "coinChange(new int[]{2}, 3)",       "fn_c": "coinChange((int[]){2},1,3)",      "fn_cpp": "([&](){ vector<int> v={2}; return coinChange(v,3); })()",       "expected": -1},
            {"fn": "coin_change([1], 0)",       "fn_js": "coinChange([1], 0)",       "fn_java": "coinChange(new int[]{1}, 0)",       "fn_c": "coinChange((int[]){1},1,0)",      "fn_cpp": "([&](){ vector<int> v={1}; return coinChange(v,0); })()",       "expected": 0},
            {"fn": "coin_change([1,2,5], 11)",  "fn_js": "coinChange([1,2,5], 11)",  "fn_java": "coinChange(new int[]{1,2,5}, 11)",  "fn_c": "coinChange((int[]){1,2,5},3,11)", "fn_cpp": "([&](){ vector<int> v={1,2,5}; return coinChange(v,11); })()",  "expected": 3},
        ],
    },

    # ══════════════════ 5. HASHING ══════════════════

    {
        "id": 13, "title": "Valid Anagram", "difficulty": "easy",
        "category": "Hashing", "tags": ["hashmap", "string", "sorting"],
        "description": "Given two strings `s` and `t`, return `true` if `t` is an anagram of `s`, and `false` otherwise.\n\nAn anagram uses all original letters exactly once in a different order.",
        "examples": [
            {"input": 's="anagram", t="nagaram"', "output": "true",  "explanation": "Same letters"},
            {"input": 's="rat", t="car"',         "output": "false", "explanation": "Different letters"},
        ],
        "starters": {
            "python":     "def is_anagram(s, t):\n    # Write your solution here\n    pass\n",
            "javascript": "function isAnagram(s, t) {\n    // Write your solution here\n    return false;\n}\n",
            "java":       "    public static boolean isAnagram(String s, String t) {\n        // Write your solution here\n        return false;\n    }\n",
            "c":          "#include <string.h>\nbool isAnagram(char* s, char* t) {\n    // Write your solution here\n    return false;\n}\n",
            "cpp":        "bool isAnagram(string s, string t) {\n    // Write your solution here\n    return false;\n}\n",
            "typescript": "function isAnagram(s: string, t: string): boolean {\n    // Write your solution here\n    return false;\n}\n",
        },
        "tests": [
            {"fn": "is_anagram('anagram','nagaram')", "fn_js": "isAnagram('anagram','nagaram')", "fn_java": "isAnagram(\"anagram\",\"nagaram\")", "fn_cpp": "isAnagram(\"anagram\",\"nagaram\")", "expected": True,  "expected_str": "true"},
            {"fn": "is_anagram('rat','car')",         "fn_js": "isAnagram('rat','car')",         "fn_java": "isAnagram(\"rat\",\"car\")",         "fn_cpp": "isAnagram(\"rat\",\"car\")",         "expected": False, "expected_str": "false"},
            {"fn": "is_anagram('a','a')",             "fn_js": "isAnagram('a','a')",             "fn_java": "isAnagram(\"a\",\"a\")",             "fn_cpp": "isAnagram(\"a\",\"a\")",             "expected": True,  "expected_str": "true"},
            {"fn": "is_anagram('ab','a')",            "fn_js": "isAnagram('ab','a')",            "fn_java": "isAnagram(\"ab\",\"a\")",            "fn_cpp": "isAnagram(\"ab\",\"a\")",            "expected": False, "expected_str": "false"},
            {"fn": "is_anagram('listen','silent')",   "fn_js": "isAnagram('listen','silent')",   "fn_java": "isAnagram(\"listen\",\"silent\")",   "fn_cpp": "isAnagram(\"listen\",\"silent\")",   "expected": True,  "expected_str": "true"},
        ],
    },
    {
        "id": 14, "title": "Two Sum (HashMap)", "difficulty": "medium",
        "category": "Hashing", "tags": ["hashmap", "array"],
        "description": "Revisit Two Sum with a focus on **HashMap approach**.\n\nGiven `nums` and `target`, return the indices of the two numbers that add up to `target` using a **single-pass HashMap** for O(n) time.\n\nExplain your approach in a comment before writing the code.",
        "examples": [
            {"input": "nums=[2,7,11,15], target=9", "output": "[0,1]", "explanation": "One-pass: store seen values in map"},
            {"input": "nums=[3,2,4], target=6",     "output": "[1,2]", "explanation": ""},
        ],
        "starters": {
            "python":     "def two_sum_map(nums, target):\n    # Use a dictionary: val -> index\n    pass\n",
            "javascript": "function twoSumMap(nums, target) {\n    // Use a Map: val -> index\n    return [];\n}\n",
            "java":       "    public static int[] twoSumMap(int[] nums, int target) {\n        // Use a HashMap: val -> index\n        return new int[]{};\n    }\n",
            "c":          "// Simple O(n^2) approach for C (no built-in hashmap)\nint* twoSumMap(int* nums, int n, int target, int* sz) {\n    *sz = 2;\n    int* r = (int*)malloc(2*sizeof(int));\n    for(int i=0;i<n;i++) for(int j=i+1;j<n;j++) if(nums[i]+nums[j]==target){r[0]=i;r[1]=j;return r;}\n    return r;\n}\n",
            "cpp":        "vector<int> twoSumMap(vector<int>& nums, int target) {\n    unordered_map<int,int> seen;\n    // Write your solution here\n    return {};\n}\n",
            "typescript": "function twoSumMap(nums: number[], target: number): number[] {\n    const map = new Map<number, number>();\n    // Write your solution here\n    return [];\n}\n",
        },
        "tests": [
            {"fn": "two_sum_map([2,7,11,15], 9)", "fn_js": "JSON.stringify(twoSumMap([2,7,11,15],9))", "fn_java": "java.util.Arrays.toString(twoSumMap(new int[]{2,7,11,15},9))", "fn_cpp": "([&](){ vector<int> v={2,7,11,15}; auto r=twoSumMap(v,9); return to_string(r[0])+\",\"+to_string(r[1]); })()", "expected": [0,1], "expected_str": "[0,1]"},
            {"fn": "two_sum_map([3,2,4], 6)",     "fn_js": "JSON.stringify(twoSumMap([3,2,4],6))",     "fn_java": "java.util.Arrays.toString(twoSumMap(new int[]{3,2,4},6))",     "fn_cpp": "([&](){ vector<int> v={3,2,4};     auto r=twoSumMap(v,6); return to_string(r[0])+\",\"+to_string(r[1]); })()", "expected": [1,2], "expected_str": "[1,2]"},
            {"fn": "two_sum_map([3,3], 6)",        "fn_js": "JSON.stringify(twoSumMap([3,3],6))",        "fn_java": "java.util.Arrays.toString(twoSumMap(new int[]{3,3},6))",        "fn_cpp": "([&](){ vector<int> v={3,3};         auto r=twoSumMap(v,6); return to_string(r[0])+\",\"+to_string(r[1]); })()", "expected": [0,1], "expected_str": "[0,1]"},
        ],
    },
    {
        "id": 15, "title": "Longest Consecutive Sequence", "difficulty": "hard",
        "category": "Hashing", "tags": ["hashset", "array"],
        "description": "Given an unsorted integer array `nums`, return the **length of the longest consecutive elements sequence**.\n\nMust run in **O(n)** time.\n\n**Hint:** Put all numbers in a set. Only start a sequence count when `num-1` is NOT in the set.",
        "examples": [
            {"input": "nums = [100,4,200,1,3,2]",    "output": "4", "explanation": "Sequence 1,2,3,4"},
            {"input": "nums = [0,3,7,2,5,8,4,6,0,1]","output": "9", "explanation": "Sequence 0..8"},
        ],
        "starters": {
            "python":     "def longest_consecutive(nums):\n    # Write your solution here\n    pass\n",
            "javascript": "function longestConsecutive(nums) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int longestConsecutive(int[] nums) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "// Sort-based approach in C\nint compare(const void* a, const void* b) { return (*(int*)a - *(int*)b); }\nint longestConsecutive(int* nums, int n) {\n    if (n == 0) return 0;\n    qsort(nums, n, sizeof(int), compare);\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int longestConsecutive(vector<int>& nums) {\n    unordered_set<int> s(nums.begin(), nums.end());\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function longestConsecutive(nums: number[]): number {\n    const s = new Set(nums);\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "longest_consecutive([100,4,200,1,3,2])",      "fn_js": "longestConsecutive([100,4,200,1,3,2])",      "fn_java": "longestConsecutive(new int[]{100,4,200,1,3,2})",      "fn_c": "longestConsecutive((int[]){100,4,200,1,3,2},6)",      "fn_cpp": "([&](){ vector<int> v={100,4,200,1,3,2};      return longestConsecutive(v); })()", "expected": 4},
            {"fn": "longest_consecutive([0,3,7,2,5,8,4,6,0,1])", "fn_js": "longestConsecutive([0,3,7,2,5,8,4,6,0,1])", "fn_java": "longestConsecutive(new int[]{0,3,7,2,5,8,4,6,0,1})", "fn_c": "longestConsecutive((int[]){0,3,7,2,5,8,4,6,0,1},10)", "fn_cpp": "([&](){ vector<int> v={0,3,7,2,5,8,4,6,0,1}; return longestConsecutive(v); })()", "expected": 9},
            {"fn": "longest_consecutive([])",                      "fn_js": "longestConsecutive([])",                      "fn_java": "longestConsecutive(new int[]{})",                      "fn_c": "longestConsecutive(NULL,0)",                           "fn_cpp": "([&](){ vector<int> v={}; return longestConsecutive(v); })()",                    "expected": 0},
            {"fn": "longest_consecutive([1,2,0,1])",               "fn_js": "longestConsecutive([1,2,0,1])",               "fn_java": "longestConsecutive(new int[]{1,2,0,1})",               "fn_c": "longestConsecutive((int[]){1,2,0,1},4)",               "fn_cpp": "([&](){ vector<int> v={1,2,0,1}; return longestConsecutive(v); })()",               "expected": 3},
        ],
    },

    # ══════════════════ 6. TWO POINTERS ══════════════════

    {
        "id": 16, "title": "Best Time to Buy and Sell Stock", "difficulty": "easy",
        "category": "Two Pointers", "tags": ["array", "greedy"],
        "description": "Given `prices` where `prices[i]` is the price on day `i`, return the **maximum profit** from one buy-sell transaction.\n\nIf no profit is possible, return `0`.",
        "examples": [
            {"input": "prices=[7,1,5,3,6,4]", "output": "5", "explanation": "Buy at 1, sell at 6"},
            {"input": "prices=[7,6,4,3,1]",   "output": "0", "explanation": "No profit possible"},
        ],
        "starters": {
            "python":     "def max_profit(prices):\n    # Write your solution here\n    pass\n",
            "javascript": "function maxProfit(prices) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int maxProfit(int[] prices) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int maxProfit(int* prices, int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int maxProfit(vector<int>& prices) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function maxProfit(prices: number[]): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "max_profit([7,1,5,3,6,4])", "fn_js": "maxProfit([7,1,5,3,6,4])", "fn_java": "maxProfit(new int[]{7,1,5,3,6,4})", "fn_c": "maxProfit((int[]){7,1,5,3,6,4},6)", "fn_cpp": "([&](){ vector<int> v={7,1,5,3,6,4}; return maxProfit(v); })()", "expected": 5},
            {"fn": "max_profit([7,6,4,3,1])",   "fn_js": "maxProfit([7,6,4,3,1])",   "fn_java": "maxProfit(new int[]{7,6,4,3,1})",   "fn_c": "maxProfit((int[]){7,6,4,3,1},5)",   "fn_cpp": "([&](){ vector<int> v={7,6,4,3,1};   return maxProfit(v); })()", "expected": 0},
            {"fn": "max_profit([1,2])",           "fn_js": "maxProfit([1,2])",           "fn_java": "maxProfit(new int[]{1,2})",           "fn_c": "maxProfit((int[]){1,2},2)",           "fn_cpp": "([&](){ vector<int> v={1,2};           return maxProfit(v); })()", "expected": 1},
            {"fn": "max_profit([2,4,1])",         "fn_js": "maxProfit([2,4,1])",         "fn_java": "maxProfit(new int[]{2,4,1})",         "fn_c": "maxProfit((int[]){2,4,1},3)",         "fn_cpp": "([&](){ vector<int> v={2,4,1};         return maxProfit(v); })()", "expected": 2},
        ],
    },
    {
        "id": 17, "title": "Binary Search", "difficulty": "medium",
        "category": "Two Pointers", "tags": ["binary search", "array", "two-pointer"],
        "description": "Given a **sorted** array `nums` and a target, return the **index** of the target or `-1` if not found.\n\nMust run in **O(log n)** time. Do not use built-in search functions.",
        "examples": [
            {"input": "nums=[-1,0,3,5,9,12], target=9", "output": "4",  "explanation": "9 is at index 4"},
            {"input": "nums=[-1,0,3,5,9,12], target=2", "output": "-1", "explanation": "Not found"},
        ],
        "starters": {
            "python":     "def binary_search(nums, target):\n    # Write your solution here\n    pass\n",
            "javascript": "function binarySearch(nums, target) {\n    // Write your solution here\n    return -1;\n}\n",
            "java":       "    public static int binarySearch(int[] nums, int target) {\n        // Write your solution here\n        return -1;\n    }\n",
            "c":          "int binarySearch(int* nums, int n, int target) {\n    // Write your solution here\n    return -1;\n}\n",
            "cpp":        "int binarySearch(vector<int>& nums, int target) {\n    // Write your solution here\n    return -1;\n}\n",
            "typescript": "function binarySearch(nums: number[], target: number): number {\n    // Write your solution here\n    return -1;\n}\n",
        },
        "tests": [
            {"fn": "binary_search([-1,0,3,5,9,12], 9)",  "fn_js": "binarySearch([-1,0,3,5,9,12], 9)",  "fn_java": "binarySearch(new int[]{-1,0,3,5,9,12}, 9)",  "fn_c": "binarySearch((int[]){-1,0,3,5,9,12},6,9)",  "fn_cpp": "([&](){ vector<int> v={-1,0,3,5,9,12}; return binarySearch(v,9); })()",  "expected": 4},
            {"fn": "binary_search([-1,0,3,5,9,12], 2)",  "fn_js": "binarySearch([-1,0,3,5,9,12], 2)",  "fn_java": "binarySearch(new int[]{-1,0,3,5,9,12}, 2)",  "fn_c": "binarySearch((int[]){-1,0,3,5,9,12},6,2)",  "fn_cpp": "([&](){ vector<int> v={-1,0,3,5,9,12}; return binarySearch(v,2); })()",  "expected": -1},
            {"fn": "binary_search([5], 5)",              "fn_js": "binarySearch([5], 5)",              "fn_java": "binarySearch(new int[]{5}, 5)",              "fn_c": "binarySearch((int[]){5},1,5)",              "fn_cpp": "([&](){ vector<int> v={5};             return binarySearch(v,5); })()",              "expected": 0},
            {"fn": "binary_search([1,3,5,7,9], 7)",     "fn_js": "binarySearch([1,3,5,7,9], 7)",     "fn_java": "binarySearch(new int[]{1,3,5,7,9}, 7)",     "fn_c": "binarySearch((int[]){1,3,5,7,9},5,7)",     "fn_cpp": "([&](){ vector<int> v={1,3,5,7,9};     return binarySearch(v,7); })()",     "expected": 3},
            {"fn": "binary_search([1,3,5,7,9], 6)",     "fn_js": "binarySearch([1,3,5,7,9], 6)",     "fn_java": "binarySearch(new int[]{1,3,5,7,9}, 6)",     "fn_c": "binarySearch((int[]){1,3,5,7,9},5,6)",     "fn_cpp": "([&](){ vector<int> v={1,3,5,7,9};     return binarySearch(v,6); })()",     "expected": -1},
        ],
    },
    {
        "id": 18, "title": "Trapping Rain Water", "difficulty": "hard",
        "category": "Two Pointers", "tags": ["array", "two-pointer", "stack"],
        "description": "Given `n` non-negative integers representing an elevation map (width=1 each), compute how much water can be **trapped** after raining.\n\n**Hint:** Two-pointer approach — track max_left and max_right from each end.",
        "examples": [
            {"input": "height=[0,1,0,2,1,0,1,3,2,1,2,1]", "output": "6", "explanation": "6 units trapped"},
            {"input": "height=[4,2,0,3,2,5]",              "output": "9", "explanation": "9 units trapped"},
        ],
        "starters": {
            "python":     "def trap(height):\n    # Write your solution here\n    pass\n",
            "javascript": "function trap(height) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int trap(int[] height) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int trap(int* height, int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int trap(vector<int>& height) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function trap(height: number[]): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "trap([0,1,0,2,1,0,1,3,2,1,2,1])", "fn_js": "trap([0,1,0,2,1,0,1,3,2,1,2,1])", "fn_java": "trap(new int[]{0,1,0,2,1,0,1,3,2,1,2,1})", "fn_c": "trap((int[]){0,1,0,2,1,0,1,3,2,1,2,1},12)", "fn_cpp": "([&](){ vector<int> v={0,1,0,2,1,0,1,3,2,1,2,1}; return trap(v); })()", "expected": 6},
            {"fn": "trap([4,2,0,3,2,5])",              "fn_js": "trap([4,2,0,3,2,5])",              "fn_java": "trap(new int[]{4,2,0,3,2,5})",              "fn_c": "trap((int[]){4,2,0,3,2,5},6)",              "fn_cpp": "([&](){ vector<int> v={4,2,0,3,2,5};              return trap(v); })()", "expected": 9},
            {"fn": "trap([])",                          "fn_js": "trap([])",                          "fn_java": "trap(new int[]{})",                          "fn_c": "trap(NULL,0)",                              "fn_cpp": "([&](){ vector<int> v={}; return trap(v); })()",                          "expected": 0},
            {"fn": "trap([1,0,1])",                    "fn_js": "trap([1,0,1])",                    "fn_java": "trap(new int[]{1,0,1})",                    "fn_c": "trap((int[]){1,0,1},3)",                    "fn_cpp": "([&](){ vector<int> v={1,0,1}; return trap(v); })()",                    "expected": 1},
        ],
    },

    # ══════════════════ 7. RECURSION ══════════════════

    {
        "id": 19, "title": "Power of Two", "difficulty": "easy",
        "category": "Recursion", "tags": ["recursion", "bit manipulation", "math"],
        "description": "Given an integer `n`, return `true` if it is a power of two, otherwise `false`.\n\nAn integer is a power of two if there exists an integer `x` such that `n == 2^x`.\n\n**Hint:** Think about the binary representation of powers of 2.",
        "examples": [
            {"input": "n = 1",  "output": "true",  "explanation": "2^0 = 1"},
            {"input": "n = 3",  "output": "false", "explanation": "Not a power of 2"},
            {"input": "n = 16", "output": "true",  "explanation": "2^4 = 16"},
        ],
        "starters": {
            "python":     "def is_power_of_two(n):\n    # Write your solution here\n    pass\n",
            "javascript": "function isPowerOfTwo(n) {\n    // Write your solution here\n    return false;\n}\n",
            "java":       "    public static boolean isPowerOfTwo(int n) {\n        // Write your solution here\n        return false;\n    }\n",
            "c":          "bool isPowerOfTwo(int n) {\n    // Write your solution here\n    return false;\n}\n",
            "cpp":        "bool isPowerOfTwo(int n) {\n    // Write your solution here\n    return false;\n}\n",
            "typescript": "function isPowerOfTwo(n: number): boolean {\n    // Write your solution here\n    return false;\n}\n",
        },
        "tests": [
            {"fn": "is_power_of_two(1)",  "fn_js": "isPowerOfTwo(1)",  "fn_java": "isPowerOfTwo(1)",  "fn_c": "isPowerOfTwo(1)",  "fn_cpp": "isPowerOfTwo(1)",  "expected": True,  "expected_str": "true"},
            {"fn": "is_power_of_two(16)", "fn_js": "isPowerOfTwo(16)", "fn_java": "isPowerOfTwo(16)", "fn_c": "isPowerOfTwo(16)", "fn_cpp": "isPowerOfTwo(16)", "expected": True,  "expected_str": "true"},
            {"fn": "is_power_of_two(3)",  "fn_js": "isPowerOfTwo(3)",  "fn_java": "isPowerOfTwo(3)",  "fn_c": "isPowerOfTwo(3)",  "fn_cpp": "isPowerOfTwo(3)",  "expected": False, "expected_str": "false"},
            {"fn": "is_power_of_two(0)",  "fn_js": "isPowerOfTwo(0)",  "fn_java": "isPowerOfTwo(0)",  "fn_c": "isPowerOfTwo(0)",  "fn_cpp": "isPowerOfTwo(0)",  "expected": False, "expected_str": "false"},
            {"fn": "is_power_of_two(64)", "fn_js": "isPowerOfTwo(64)", "fn_java": "isPowerOfTwo(64)", "fn_c": "isPowerOfTwo(64)", "fn_cpp": "isPowerOfTwo(64)", "expected": True,  "expected_str": "true"},
        ],
    },
    {
        "id": 20, "title": "Subsets", "difficulty": "medium",
        "category": "Recursion", "tags": ["backtracking", "array"],
        "description": "Given an integer array `nums` of **unique** elements, return all possible subsets (the power set).\n\nThe solution must not contain duplicate subsets.",
        "examples": [
            {"input": "nums=[1,2,3]", "output": "[[],[1],[2],[3],[1,2],[1,3],[2,3],[1,2,3]]", "explanation": "8 subsets"},
            {"input": "nums=[0]",     "output": "[[],[0]]",                                    "explanation": "2 subsets"},
        ],
        "starters": {
            "python":     "def subsets(nums):\n    # Write your solution here\n    pass\n",
            "javascript": "function subsets(nums) {\n    // Write your solution here\n    return [[]];\n}\n",
            "java":       "    public static java.util.List<java.util.List<Integer>> subsets(int[] nums) {\n        // Write your solution here\n        return new java.util.ArrayList<>();\n    }\n",
            "c":          "// Returns count of subsets (2^n)\nint subsetsCount(int* nums, int n) {\n    int count = 1;\n    for (int i = 0; i < n; i++) count *= 2;\n    return count;\n}\n",
            "cpp":        "vector<vector<int>> subsets(vector<int>& nums) {\n    // Write your solution here\n    return {{}};\n}\n",
            "typescript": "function subsets(nums: number[]): number[][] {\n    // Write your solution here\n    return [[]];\n}\n",
        },
        "tests": [
            {"fn": "len(subsets([1,2,3]))",                         "fn_js": "subsets([1,2,3]).length",         "fn_java": "subsets(new int[]{1,2,3}).size()",   "fn_c": "subsetsCount((int[]){1,2,3},3)", "fn_cpp": "([&](){ vector<int> v={1,2,3}; return (int)subsets(v).size(); })()", "expected": 8},
            {"fn": "sorted([sorted(s) for s in subsets([1,2,3])])", "fn_js": "subsets([1,2,3]).length === 8",   "fn_java": "subsets(new int[]{1,2,3}).size()==8","fn_c": "subsetsCount((int[]){1,2,3},3)", "fn_cpp": "([&](){ vector<int> v={1,2,3}; return (int)subsets(v).size(); })()", "expected": [[],[1],[1,2],[1,2,3],[1,3],[2],[2,3],[3]]},
            {"fn": "len(subsets([0]))",                             "fn_js": "subsets([0]).length",             "fn_java": "subsets(new int[]{0}).size()",       "fn_c": "subsetsCount((int[]){0},1)",    "fn_cpp": "([&](){ vector<int> v={0}; return (int)subsets(v).size(); })()", "expected": 2},
            {"fn": "len(subsets([1,2,3,4]))",                       "fn_js": "subsets([1,2,3,4]).length",       "fn_java": "subsets(new int[]{1,2,3,4}).size()", "fn_c": "subsetsCount((int[]){1,2,3,4},4)","fn_cpp": "([&](){ vector<int> v={1,2,3,4}; return (int)subsets(v).size(); })()", "expected": 16},
        ],
    },
    {
        "id": 21, "title": "N-Queens Count", "difficulty": "hard",
        "category": "Recursion", "tags": ["backtracking", "matrix", "constraint"],
        "description": "Place `n` queens on an `n×n` board so no two queens attack each other.\n\nReturn the **number of distinct solutions**.\n\n**Hint:** Backtracking with sets for columns and both diagonals.",
        "examples": [
            {"input": "n = 4", "output": "2",  "explanation": "Two valid arrangements"},
            {"input": "n = 1", "output": "1",  "explanation": "Trivial"},
            {"input": "n = 5", "output": "10", "explanation": "Ten valid arrangements"},
        ],
        "starters": {
            "python":     "def total_n_queens(n):\n    # Write your solution here\n    pass\n",
            "javascript": "function totalNQueens(n) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int totalNQueens(int n) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "int totalNQueens(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "cpp":        "int totalNQueens(int n) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function totalNQueens(n: number): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "total_n_queens(1)", "fn_js": "totalNQueens(1)", "fn_java": "totalNQueens(1)", "fn_c": "totalNQueens(1)", "fn_cpp": "totalNQueens(1)", "expected": 1},
            {"fn": "total_n_queens(4)", "fn_js": "totalNQueens(4)", "fn_java": "totalNQueens(4)", "fn_c": "totalNQueens(4)", "fn_cpp": "totalNQueens(4)", "expected": 2},
            {"fn": "total_n_queens(5)", "fn_js": "totalNQueens(5)", "fn_java": "totalNQueens(5)", "fn_c": "totalNQueens(5)", "fn_cpp": "totalNQueens(5)", "expected": 10},
            {"fn": "total_n_queens(6)", "fn_js": "totalNQueens(6)", "fn_java": "totalNQueens(6)", "fn_c": "totalNQueens(6)", "fn_cpp": "totalNQueens(6)", "expected": 4},
            {"fn": "total_n_queens(8)", "fn_js": "totalNQueens(8)", "fn_java": "totalNQueens(8)", "fn_c": "totalNQueens(8)", "fn_cpp": "totalNQueens(8)", "expected": 92},
        ],
    },

    # ══════════════════ 8. SORTING & SEARCHING ══════════════════

    {
        "id": 22, "title": "Merge Sorted Arrays", "difficulty": "easy",
        "category": "Sorting & Searching", "tags": ["sorting", "array", "two-pointer"],
        "description": "Given two sorted arrays `a` and `b`, return a new sorted array containing all elements from both.\n\nDo **not** use the built-in sort function. Use the merge step from merge sort.",
        "examples": [
            {"input": "a=[1,3,5], b=[2,4,6]", "output": "[1,2,3,4,5,6]", "explanation": "Merged in order"},
            {"input": "a=[1], b=[2,3,4]",     "output": "[1,2,3,4]",     "explanation": ""},
        ],
        "starters": {
            "python":     "def merge_sorted(a, b):\n    # Write your solution here\n    pass\n",
            "javascript": "function mergeSorted(a, b) {\n    // Write your solution here\n    return [];\n}\n",
            "java":       "    public static int[] mergeSorted(int[] a, int[] b) {\n        // Write your solution here\n        return new int[]{};\n    }\n",
            "c":          "void mergeSorted(int* a, int na, int* b, int nb, int* out) {\n    int i=0,j=0,k=0;\n    // Write your solution here\n}\n",
            "cpp":        "vector<int> mergeSorted(vector<int>& a, vector<int>& b) {\n    // Write your solution here\n    return {};\n}\n",
            "typescript": "function mergeSorted(a: number[], b: number[]): number[] {\n    // Write your solution here\n    return [];\n}\n",
        },
        "tests": [
            {"fn": "merge_sorted([1,3,5],[2,4,6])", "fn_js": "JSON.stringify(mergeSorted([1,3,5],[2,4,6]))", "fn_java": "java.util.Arrays.toString(mergeSorted(new int[]{1,3,5},new int[]{2,4,6}))", "fn_cpp": "([&](){ vector<int> a={1,3,5},b={2,4,6}; auto r=mergeSorted(a,b); string s=\"[\"; for(int x:r)s+=to_string(x)+\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()", "expected": [1,2,3,4,5,6]},
            {"fn": "merge_sorted([1],[2,3,4])",     "fn_js": "JSON.stringify(mergeSorted([1],[2,3,4]))",     "fn_java": "java.util.Arrays.toString(mergeSorted(new int[]{1},new int[]{2,3,4}))",     "fn_cpp": "([&](){ vector<int> a={1},b={2,3,4}; auto r=mergeSorted(a,b); string s=\"[\"; for(int x:r)s+=to_string(x)+\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()",     "expected": [1,2,3,4]},
            {"fn": "merge_sorted([],[1,2])",        "fn_js": "JSON.stringify(mergeSorted([],[1,2]))",        "fn_java": "java.util.Arrays.toString(mergeSorted(new int[]{},new int[]{1,2}))",        "fn_cpp": "([&](){ vector<int> a={},b={1,2}; auto r=mergeSorted(a,b); string s=\"[\"; for(int x:r)s+=to_string(x)+\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()",        "expected": [1,2]},
            {"fn": "merge_sorted([5],[1])",         "fn_js": "JSON.stringify(mergeSorted([5],[1]))",         "fn_java": "java.util.Arrays.toString(mergeSorted(new int[]{5},new int[]{1}))",         "fn_cpp": "([&](){ vector<int> a={5},b={1}; auto r=mergeSorted(a,b); string s=\"[\"; for(int x:r)s+=to_string(x)+\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()",         "expected": [1,5]},
        ],
    },
    {
        "id": 23, "title": "Kth Largest Element", "difficulty": "medium",
        "category": "Sorting & Searching", "tags": ["sorting", "heap", "quickselect"],
        "description": "Given an integer array `nums` and an integer `k`, return the **k-th largest** element.\n\nNote: k-th largest in sorted order, not k-th distinct.\n\n**Hint:** Sort in O(n log n) or use a min-heap for better performance.",
        "examples": [
            {"input": "nums=[3,2,1,5,6,4], k=2",    "output": "5", "explanation": "2nd largest is 5"},
            {"input": "nums=[3,2,3,1,2,4,5,5,6], k=4","output":"4","explanation": "4th largest is 4"},
        ],
        "starters": {
            "python":     "def find_kth_largest(nums, k):\n    # Write your solution here\n    pass\n",
            "javascript": "function findKthLargest(nums, k) {\n    // Write your solution here\n    return 0;\n}\n",
            "java":       "    public static int findKthLargest(int[] nums, int k) {\n        // Write your solution here\n        return 0;\n    }\n",
            "c":          "#include <stdlib.h>\nint cmp(const void* a, const void* b) { return *(int*)b - *(int*)a; }\nint findKthLargest(int* nums, int n, int k) {\n    qsort(nums, n, sizeof(int), cmp);\n    return nums[k-1];\n}\n",
            "cpp":        "int findKthLargest(vector<int>& nums, int k) {\n    // Write your solution here\n    return 0;\n}\n",
            "typescript": "function findKthLargest(nums: number[], k: number): number {\n    // Write your solution here\n    return 0;\n}\n",
        },
        "tests": [
            {"fn": "find_kth_largest([3,2,1,5,6,4], 2)",    "fn_js": "findKthLargest([3,2,1,5,6,4], 2)",    "fn_java": "findKthLargest(new int[]{3,2,1,5,6,4}, 2)",    "fn_c": "findKthLargest((int[]){3,2,1,5,6,4},6,2)",    "fn_cpp": "([&](){ vector<int> v={3,2,1,5,6,4};   return findKthLargest(v,2); })()", "expected": 5},
            {"fn": "find_kth_largest([3,2,3,1,2,4,5,5,6],4)","fn_js": "findKthLargest([3,2,3,1,2,4,5,5,6],4)","fn_java":"findKthLargest(new int[]{3,2,3,1,2,4,5,5,6},4)","fn_c": "findKthLargest((int[]){3,2,3,1,2,4,5,5,6},9,4)","fn_cpp": "([&](){ vector<int> v={3,2,3,1,2,4,5,5,6}; return findKthLargest(v,4); })()", "expected": 4},
            {"fn": "find_kth_largest([1], 1)",               "fn_js": "findKthLargest([1], 1)",               "fn_java": "findKthLargest(new int[]{1}, 1)",               "fn_c": "findKthLargest((int[]){1},1,1)",               "fn_cpp": "([&](){ vector<int> v={1};             return findKthLargest(v,1); })()", "expected": 1},
            {"fn": "find_kth_largest([2,1], 1)",             "fn_js": "findKthLargest([2,1], 1)",             "fn_java": "findKthLargest(new int[]{2,1}, 1)",             "fn_c": "findKthLargest((int[]){2,1},2,1)",             "fn_cpp": "([&](){ vector<int> v={2,1};           return findKthLargest(v,1); })()", "expected": 2},
        ],
    },
    {
        "id": 24, "title": "Sort Colors (Dutch Flag)", "difficulty": "hard",
        "category": "Sorting & Searching", "tags": ["sorting", "two-pointer", "in-place"],
        "description": "Given an array `nums` with values 0, 1, and 2 (representing red, white, and blue), sort them **in-place** so that objects of the same color are adjacent, in order 0, 1, 2.\n\nDo **not** use the built-in sort function. Use the **Dutch National Flag algorithm** — O(n) time, O(1) space.",
        "examples": [
            {"input": "nums=[2,0,2,1,1,0]", "output": "[0,0,1,1,2,2]", "explanation": "Sorted in one pass"},
            {"input": "nums=[2,0,1]",        "output": "[0,1,2]",       "explanation": ""},
        ],
        "starters": {
            "python":     "def sort_colors(nums):\n    # Sort in-place. Use three pointers: lo, mid, hi\n    pass\n",
            "javascript": "function sortColors(nums) {\n    // Sort in-place using Dutch National Flag\n}\n",
            "java":       "    public static void sortColors(int[] nums) {\n        // Sort in-place using Dutch National Flag\n    }\n",
            "c":          "void sortColors(int* nums, int n) {\n    int lo=0, mid=0, hi=n-1;\n    // Write your solution here\n}\n",
            "cpp":        "void sortColors(vector<int>& nums) {\n    int lo=0, mid=0, hi=nums.size()-1;\n    // Write your solution here\n}\n",
            "typescript": "function sortColors(nums: number[]): void {\n    // Sort in-place using Dutch National Flag\n}\n",
        },
        "tests": [
            {"fn": "([lambda n: (sort_colors(n), n)[1]]([2,0,2,1,1,0]))[0]", "fn_js": "(function(){ let a=[2,0,2,1,1,0]; sortColors(a); return JSON.stringify(a); })()", "fn_java": "(new java.util.function.Supplier<String>(){ public String get(){ int[] a={2,0,2,1,1,0}; sortColors(a); return java.util.Arrays.toString(a); }}).get()", "fn_cpp": "([&](){ vector<int> v={2,0,2,1,1,0}; sortColors(v); string s=\"[\"; for(int x:v)s+=to_string(x)+\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()", "expected": [0,0,1,1,2,2]},
            {"fn": "([lambda n: (sort_colors(n), n)[1]]([2,0,1]))[0]",       "fn_js": "(function(){ let a=[2,0,1]; sortColors(a); return JSON.stringify(a); })()",       "fn_java": "(new java.util.function.Supplier<String>(){ public String get(){ int[] a={2,0,1}; sortColors(a); return java.util.Arrays.toString(a); }}).get()",       "fn_cpp": "([&](){ vector<int> v={2,0,1}; sortColors(v); string s=\"[\"; for(int x:v)s+=to_string(x)+\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()",       "expected": [0,1,2]},
            {"fn": "([lambda n: (sort_colors(n), n)[1]]([0]))[0]",            "fn_js": "(function(){ let a=[0]; sortColors(a); return JSON.stringify(a); })()",            "fn_java": "(new java.util.function.Supplier<String>(){ public String get(){ int[] a={0}; sortColors(a); return java.util.Arrays.toString(a); }}).get()",            "fn_cpp": "([&](){ vector<int> v={0}; sortColors(v); return to_string(v[0]); })()",                                                                                                                              "expected": [0]},
            {"fn": "([lambda n: (sort_colors(n), n)[1]]([1,0,0,2]))[0]",     "fn_js": "(function(){ let a=[1,0,0,2]; sortColors(a); return JSON.stringify(a); })()",     "fn_java": "(new java.util.function.Supplier<String>(){ public String get(){ int[] a={1,0,0,2}; sortColors(a); return java.util.Arrays.toString(a); }}).get()",     "fn_cpp": "([&](){ vector<int> v={1,0,0,2}; sortColors(v); string s=\"[\"; for(int x:v)s+=to_string(x)+\",\"; if(s.back()==',')s.pop_back(); s+=\"]\"; return s; })()", "expected": [0,0,1,2]},
        ],
    },
]

def run_challenge_tests(code, challenge, language="python"):
    """Execute user code in the appropriate language runtime and evaluate test cases."""
    import subprocess, tempfile, os, json, traceback, sys, platform

    is_windows = platform.system() == "Windows"
    results    = []

    # ── Python runner (exec in isolated namespace) ─────────────────
    if language == "python":
        namespace = {}
        try:
            exec(compile(code, "<user>", "exec"), namespace)
        except SyntaxError as e:
            return [{"passed": False, "fn": t["fn"], "expected": str(t["expected"]),
                     "actual": "", "error": f"SyntaxError: {e}"} for t in challenge["tests"]]
        except Exception as e:
            return [{"passed": False, "fn": t["fn"], "expected": str(t["expected"]),
                     "actual": "", "error": str(e)} for t in challenge["tests"]]

        for test in challenge["tests"]:
            try:
                actual   = eval(test["fn"], namespace)
                expected = test["expected"]
                # For tests that are boolean comparisons, eval gives bool directly
                if isinstance(expected, bool):
                    passed = actual == expected
                else:
                    passed = actual == expected
                results.append({
                    "fn": test["fn"], "expected": str(expected),
                    "actual": str(actual), "passed": passed,
                })
            except Exception:
                results.append({
                    "fn": test["fn"], "expected": str(test["expected"]),
                    "actual": "", "passed": False,
                    "error": traceback.format_exc(limit=2).strip(),
                })
        return results

    # ── JavaScript / TypeScript runner (Node.js) ───────────────────
    if language in ("javascript", "typescript"):
        tmpdir = tempfile.mkdtemp()
        try:
            # Build test harness
            test_code = code + "\n\n"
            test_code += "const __results = [];\n"
            for t in challenge["tests"]:
                fn_js  = t.get("fn_js",  t["fn"])   # JS version of fn call
                exp    = json.dumps(t["expected"])
                test_code += (
                    f"try {{ const __a = {fn_js}; "
                    f"__results.push({{fn:{json.dumps(fn_js)},expected:{exp},"
                    f"actual:JSON.stringify(__a),passed:JSON.stringify(__a)==={json.dumps(exp)}}}) }}"
                    f" catch(e) {{ __results.push({{fn:{json.dumps(fn_js)},expected:{exp},"
                    f"actual:'',passed:false,error:e.message}}) }}\n"
                )
            test_code += "console.log(JSON.stringify(__results));\n"

            src = os.path.join(tmpdir, "solution.js")
            with open(src, "w") as f:
                f.write(test_code)

            node_cmd = "node.exe" if is_windows else "node"
            r = subprocess.run([node_cmd, src], capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                err = r.stderr.strip().split("\n")[0]
                return [{"passed": False, "fn": t.get("fn_js", t["fn"]),
                         "expected": str(t["expected"]), "actual": "", "error": err}
                        for t in challenge["tests"]]
            data = json.loads(r.stdout.strip())
            for i, row in enumerate(data):
                exp_raw = challenge["tests"][i]["expected"]
                actual_parsed = json.loads(row["actual"]) if row["actual"] else None
                passed = actual_parsed == exp_raw
                results.append({
                    "fn": row["fn"], "expected": str(exp_raw),
                    "actual": row["actual"], "passed": passed,
                    **({"error": row["error"]} if row.get("error") else {})
                })
        except Exception as e:
            results = [{"passed": False, "fn": t.get("fn_js", t["fn"]),
                        "expected": str(t["expected"]), "actual": "", "error": str(e)}
                       for t in challenge["tests"]]
        finally:
            import shutil; shutil.rmtree(tmpdir, ignore_errors=True)
        return results

    # ── Java runner ────────────────────────────────────────────────
    if language == "java":
        tmpdir = tempfile.mkdtemp()
        try:
            fn_calls = []
            for t in challenge["tests"]:
                fn_java = t.get("fn_java", t["fn"])
                fn_calls.append((fn_java, t["expected"]))

            # Wrap user code in a class with main that prints JSON results
            test_stmts = ""
            for fn, exp in fn_calls:
                exp_json = json.dumps(exp)
                test_stmts += (
                    f"        try {{ Object result = {fn}; "
                    f"results.add(result + \"\t\" + {json.dumps(exp_json)}); }}"
                    f" catch(Exception e) {{ results.add(\"ERR\t\" + e.getMessage()); }}\n"
                )

            java_src = f"""import java.util.*;
public class Solution {{
{code}
    public static void main(String[] args) {{
        List<String> results = new ArrayList<>();
{test_stmts}
        for (String r : results) System.out.println(r);
    }}
}}"""
            src = os.path.join(tmpdir, "Solution.java")
            with open(src, "w") as f:
                f.write(java_src)

            javac = "javac.exe" if is_windows else "javac"
            rc = subprocess.run([javac, src], capture_output=True, text=True, timeout=15)
            if rc.returncode != 0:
                err = rc.stderr.strip().split("\n")[0]
                return [{"passed": False, "fn": t.get("fn_java", t["fn"]),
                         "expected": str(t["expected"]), "actual": "", "error": err}
                        for t in challenge["tests"]]

            java_cmd = "java.exe" if is_windows else "java"
            r = subprocess.run([java_cmd, "-cp", tmpdir, "Solution"],
                               capture_output=True, text=True, timeout=10)
            lines = r.stdout.strip().split("\n")
            for i, (fn, exp) in enumerate(fn_calls):
                if i < len(lines):
                    parts = lines[i].split("\t", 1)
                    if parts[0] == "ERR":
                        results.append({"fn": fn, "expected": str(exp), "actual": "",
                                        "passed": False, "error": parts[1] if len(parts)>1 else "Error"})
                    else:
                        actual_str = parts[0].strip()
                        passed = str(exp) == actual_str
                        results.append({"fn": fn, "expected": str(exp),
                                        "actual": actual_str, "passed": passed})
                else:
                    results.append({"fn": fn, "expected": str(exp), "actual": "",
                                    "passed": False, "error": "No output"})
        except Exception as e:
            results = [{"passed": False, "fn": t.get("fn_java", t["fn"]),
                        "expected": str(t["expected"]), "actual": "", "error": str(e)}
                       for t in challenge["tests"]]
        finally:
            import shutil; shutil.rmtree(tmpdir, ignore_errors=True)
        return results

    # ── C runner ───────────────────────────────────────────────────
    if language == "c":
        tmpdir = tempfile.mkdtemp()
        try:
            fn_calls = [(t.get("fn_c", t["fn"]), t["expected"], t.get("fmt_c", "%d")) for t in challenge["tests"]]
            prints   = "".join(f'    printf("{fmt}\\n", {fn});\n' for fn, exp, fmt in fn_calls)
            c_src    = f"#include <stdio.h>\n#include <string.h>\n#include <stdbool.h>\n\n{code}\n\nint main() {{\n{prints}    return 0;\n}}\n"

            src = os.path.join(tmpdir, "solution.c")
            exe = os.path.join(tmpdir, "solution.exe" if is_windows else "solution")
            with open(src, "w") as f:
                f.write(c_src)
            rc = subprocess.run(["gcc", src, "-o", exe, "-lm"], capture_output=True, text=True, timeout=15)
            if rc.returncode != 0:
                err = rc.stderr.strip().split("\n")[0]
                return [{"passed": False, "fn": t.get("fn_c", t["fn"]),
                         "expected": str(t["expected"]), "actual": "", "error": err}
                        for t in challenge["tests"]]

            r = subprocess.run([exe], capture_output=True, text=True, timeout=5)
            lines = r.stdout.strip().split("\n")
            for i, (fn, exp, fmt) in enumerate(fn_calls):
                actual_str = lines[i].strip() if i < len(lines) else ""
                if isinstance(exp, bool):
                    passed = actual_str == ("1" if exp else "0")
                else:
                    passed = str(exp) == actual_str
                results.append({"fn": fn, "expected": str(exp),
                                 "actual": actual_str, "passed": passed})
        except Exception as e:
            results = [{"passed": False, "fn": t.get("fn_c", t["fn"]),
                        "expected": str(t["expected"]), "actual": "", "error": str(e)}
                       for t in challenge["tests"]]
        finally:
            import shutil; shutil.rmtree(tmpdir, ignore_errors=True)
        return results

    # ── C++ runner ─────────────────────────────────────────────────
    if language == "cpp":
        tmpdir = tempfile.mkdtemp()
        try:
            fn_calls = [(t.get("fn_cpp", t.get("fn_c", t["fn"])), t["expected"], t.get("fmt_c", "%d")) for t in challenge["tests"]]
            prints   = "".join(f'    std::cout << {fn} << "\\n";\n' for fn, exp, _ in fn_calls)
            cpp_src  = f"#include <iostream>\n#include <vector>\n#include <string>\n#include <algorithm>\n#include <unordered_map>\n#include <unordered_set>\n#include <queue>\n#include <cmath>\n#include <climits>\nusing namespace std;\n\n{code}\n\nint main() {{\n{prints}    return 0;\n}}\n"

            src = os.path.join(tmpdir, "solution.cpp")
            exe = os.path.join(tmpdir, "solution.exe" if is_windows else "solution")
            with open(src, "w") as f:
                f.write(cpp_src)
            rc = subprocess.run(["g++", "-std=c++17", src, "-o", exe], capture_output=True, text=True, timeout=15)
            if rc.returncode != 0:
                err = rc.stderr.strip().split("\n")[0]
                return [{"passed": False, "fn": t.get("fn_cpp", t.get("fn_c", t["fn"])),
                         "expected": str(t["expected"]), "actual": "", "error": err}
                        for t in challenge["tests"]]

            r = subprocess.run([exe], capture_output=True, text=True, timeout=5)
            lines = r.stdout.strip().split("\n")
            for i, (fn, exp, _) in enumerate(fn_calls):
                actual_str = lines[i].strip() if i < len(lines) else ""
                # Handle C++ bool output (prints 1/0 instead of true/false)
                if isinstance(exp, bool):
                    passed = actual_str == ("1" if exp else "0")
                else:
                    passed = str(exp) == actual_str
                results.append({"fn": fn, "expected": str(exp),
                                 "actual": actual_str, "passed": passed})
        except Exception as e:
            results = [{"passed": False, "fn": t.get("fn_cpp", t.get("fn_c", t["fn"])),
                        "expected": str(t["expected"]), "actual": "", "error": str(e)}
                       for t in challenge["tests"]]
        finally:
            import shutil; shutil.rmtree(tmpdir, ignore_errors=True)
        return results

    # ── Fallback: unsupported language ─────────────────────────────
    return [{"passed": False, "fn": t["fn"], "expected": str(t["expected"]),
             "actual": "", "error": f"Language '{language}' runner not available on this server. Use Python, JavaScript, C, or C++."}
            for t in challenge["tests"]]


@editor_bp.route("/challenges")
@login_required
def challenges():
    db  = get_db()
    uid = session["user_id"]
    solved = set(
        r["challenge_id"] for r in db.execute(
            "SELECT DISTINCT challenge_id FROM challenge_attempts WHERE user_id=? AND passed=1",
            (uid,)
        ).fetchall()
    )
    return render_template("challenges.html", challenges=CHALLENGES, solved=solved)


@editor_bp.route("/challenges/<int:cid>")
@login_required
def challenge_detail(cid):
    ch = next((c for c in CHALLENGES if c["id"] == cid), None)
    if not ch:
        return redirect(url_for("editor.challenges"))
    db   = get_db()
    uid  = session["user_id"]
    best = db.execute(
        "SELECT * FROM challenge_attempts WHERE user_id=? AND challenge_id=? ORDER BY passed DESC, created_at DESC LIMIT 1",
        (uid, cid)
    ).fetchone()
    return render_template("challenge_detail.html", challenge=ch, best=best)


@editor_bp.route("/api/challenges/<int:cid>/run", methods=["POST"])
@login_required
def run_challenge(cid):
    ch = next((c for c in CHALLENGES if c["id"] == cid), None)
    if not ch:
        return jsonify({"error": "Not found"}), 404
    data     = request.get_json()
    code     = data.get("code", "").strip()
    language = data.get("language", "python").lower()
    if not code:
        return jsonify({"error": "No code provided"}), 400

    results    = run_challenge_tests(code, ch, language)
    passed_all = all(r["passed"] for r in results)
    score      = sum(1 for r in results if r["passed"])
    total      = len(results)

    try:
        db = get_db()
        db.execute(
            "INSERT INTO challenge_attempts (user_id, challenge_id, title, difficulty, code, score, total, passed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session["user_id"], cid, ch["title"], ch["difficulty"],
             code, score, total, 1 if passed_all else 0,
             datetime.datetime.now().isoformat())
        )
        db.commit()
    except Exception as e:
        print(f"Challenge save error: {e}")

    return jsonify({"results": results, "passed_all": passed_all, "score": score, "total": total})
