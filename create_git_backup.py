"""创建git备份"""
import subprocess, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 忽略数据文件和缓存
gitignore = """__pycache__/
*.pyc
.DS_Store
reasonix.toml
.reasonix/
*.parquet
*.csv
.env
"""

with open('.gitignore', 'w') as f:
    f.write(gitignore)

subprocess.run(['git', 'init'], check=True)
subprocess.run(['git', 'add', '-A'], check=True)
subprocess.run(['git', 'commit', '-m', '初始备份: CryptoPulse v1', '--allow-empty'], check=True)
print("✅ Git 仓库已创建并提交！")
print("以后可以随时回滚: git checkout -- cryptopulse/api/app.py")
