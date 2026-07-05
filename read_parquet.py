import pandas as pd, os, glob

data_dir = 'cryptopulse/data/BTC-USDT-SWAP'
for f in sorted(os.listdir(data_dir)):
    if not f.endswith('.parquet'):
        continue
    path = os.path.join(data_dir, f)
    size_mb = os.path.getsize(path) / 1024 / 1024
    df = pd.read_parquet(path)
    cols = list(df.columns)
    time_col = None
    for c in ['timestamp', 'time', 'open_time', 'datetime', 'date']:
        if c in cols:
            time_col = c
            break
    if time_col:
        t_min = df[time_col].min()
        t_max = df[time_col].max()
        cnt = len(df)
        print(f'{f:25s}  {cnt:8,d}条  {size_mb:6.2f}MB  [{t_min}]  ~  [{t_max}]')
    else:
        idx_name = df.index.name
        if idx_name and idx_name in ('timestamp', 'time', 'datetime'):
            t_min = df.index.min()
            t_max = df.index.max()
            cnt = len(df)
            print(f'{f:25s}  {cnt:8,d}条  {size_mb:6.2f}MB  [{t_min}]  ~  [{t_max}]')
        else:
            print(f'{f:25s}  {len(df):8,d}条  {size_mb:6.2f}MB  列: {cols}  索引: {idx_name}')
