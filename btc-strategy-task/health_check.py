#!/usr/bin/env python3
"""
BTC合约任务自检脚本 v1.0
- 每30分钟执行一次自动检查
- 检查API数据获取、任务运行状态、策略执行
- 发现问题自动修复并记录
"""
import ccxt
import os
import json
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path

# ========== 路径配置 ==========
TASK_DIR = '/root/.openclaw/workspace/btc-strategy-task'
AUTO_TRADE_SCRIPT = f'{TASK_DIR}/auto_trade.py'
STATE_FILE = f'{TASK_DIR}/databases/state.json'
WORK_LOG = f'{TASK_DIR}/logs/work_log.txt'
STATS_FILE = f'{TASK_DIR}/databases/trade_stats.json'
LOG_DIR = f'{TASK_DIR}/logs/health_check'
FIX_LOG = f'{LOG_DIR}/fix_log.txt'
CHECK_LOG = f'{LOG_DIR}/check_log.json'
NOTIFY_QUEUE = f'{TASK_DIR}/databases/notify_queue.json'

# API配置
API_KEY = "CUPwmVULosVO24NBKmoaMm0pvga2msasOa4nBhvPvybrGdA2RcXBYA4aRtGMZjWH"
SECRET = "Ozht5MjazUu4JKhSLqx4ASmTBH4wlUMdbABOblxXGyhIuof1jhrzUEr9JkWHpUHM"
SYMBOL = 'BTC/USDT:USDT'

os.makedirs(LOG_DIR, exist_ok=True)

# ========== 日志工具 ==========
def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    return line

def get_data():
    """获取所有周期数据"""
    binance = ccxt.binance({
        'apiKey': API_KEY,
        'secret': SECRET,
        'options': {'defaultType': 'swap', 'defaultPositionSide': 'LONG', 'marginMode': 'cross'}
    })
    k5m = binance.fetch_ohlcv(SYMBOL, timeframe='5m', limit=100)
    k1h = binance.fetch_ohlcv(SYMBOL, timeframe='1h', limit=200)
    k4h = binance.fetch_ohlcv(SYMBOL, timeframe='4h', limit=200)
    k1d = binance.fetch_ohlcv(SYMBOL, timeframe='1d', limit=200)
    return {'k5m': k5m, 'k1h': k1h, 'k4h': k4h, 'k1d': k1d}

# ========== 自检项 ==========
class HealthChecker:
    def __init__(self):
        self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.results = []
        self.fixes = []
        self.checks_ok = 0
        self.checks_fail = 0

    def add_ok(self, item, detail=''):
        self.checks_ok += 1
        self.results.append({
            'time': self.timestamp,
            'item': item,
            'status': '✅ OK',
            'detail': detail
        })
        log(f"✅ {item}: {detail or '正常'}")

    def add_fail(self, item, detail='', fix=None):
        self.checks_fail += 1
        self.results.append({
            'time': self.timestamp,
            'item': item,
            'status': '❌ FAIL',
            'detail': detail,
            'fix': fix
        })
        log(f"❌ {item}: {detail}")
        if fix:
            log(f"   🔧 修复: {fix}")

    def check_process(self):
        """检查1: 进程是否运行"""
        try:
            result = subprocess.run(
                ['ps', 'aux'], capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if 'auto_trade.py' in line and 'grep' not in line:
                    parts = line.split()
                    pid = parts[1]
                    # 计算运行时长
                    start_time_idx = parts[5] if len(parts) > 5 else '?'
                    self.add_ok('进程状态', f'PID={pid}, 启动时间={start_time_idx}')
                    return True
            self.add_fail('进程状态', '进程未运行', fix='重启auto_trade.py')
            return False
        except Exception as e:
            self.add_fail('进程状态', f'检查失败: {e}')
            return False

    def check_api_data(self):
        """检查2: API数据获取"""
        try:
            data = get_data()
            required = {'k5m': '5分钟', 'k1h': '1小时', 'k4h': '4小时', 'k1d': '1天'}
            for key, name in required.items():
                if key not in data or len(data[key]) < 50:
                    self.add_fail(f'API-{name}', f'数据不足: {len(data.get(key, []))}条', fix='等待下次重试')
                    return False
                if data[key][-1][1] is None:
                    self.add_fail(f'API-{name}', '最新K线收盘价为None', fix='等待下一根K线')
                    return False
            
            price = data['k5m'][-1][2]  # high
            self.add_ok('API数据', f'各周期数据正常，最新价格=${price}')
            return True
        except ccxt.NetworkError as e:
            self.add_fail('API-网络', f'网络错误: {e}', fix='检查网络连接')
            return False
        except Exception as e:
            self.add_fail('API-数据', f'获取失败: {e}', fix='重启任务进程')
            return False

    def check_api_endpoints(self):
        """检查3: 各API端口状态"""
        endpoints = [
            ('fetch_ticker', '当前价格'),
            ('fetch_balance', '账户余额'),
            ('fetch_positions', '持仓信息'),
        ]
        try:
            binance = ccxt.binance({
                'apiKey': API_KEY,
                'secret': SECRET,
                'options': {'defaultType': 'swap', 'defaultPositionSide': 'LONG', 'marginMode': 'cross'}
            })
            for method, name in endpoints:
                try:
                    if method == 'fetch_ticker':
                        r = binance.fetch_ticker(SYMBOL)
                        if 'last' in r and r['last']:
                            self.add_ok(f'API-{name}', f'${r["last"]}')
                        else:
                            self.add_fail(f'API-{name}', '无价格数据')
                    elif method == 'fetch_balance':
                        # 用不带positionSide的client查询余额
                        bal_binance = ccxt.binance({'apiKey': API_KEY, 'secret': SECRET, 'options': {'defaultType': 'swap'}})
                        r = bal_binance.fetch_balance()
                        usdt = r.get('USDT', {})
                        usdt_free = usdt.get('free', 0)
                        usdt_total = usdt.get('total', 0)
                        self.add_ok(f'API-{name}', f'USDT可用={usdt_free}, 总计={usdt_total}')
                    elif method == 'fetch_positions':
                        r = binance.fetch_positions([SYMBOL])
                        self.add_ok(f'API-{name}', f'持仓数={len(r)}')
                except Exception as e:
                    self.add_fail(f'API-{name}', str(e)[:50], fix=f'{method}接口异常')
            return True
        except Exception as e:
            self.add_fail('API-端口', f'初始化失败: {e}')
            return False

    def check_strategy(self):
        """检查4: 策略执行状态"""
        try:
            # 检查state.json
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    state = json.load(f)
                self.add_ok('State文件', f'in_position={state.get("in_position", False)}')
            else:
                self.add_fail('State文件', '文件不存在', fix='创建默认state')
                with open(STATE_FILE, 'w') as f:
                    json.dump({'in_position': False}, f)

            # 检查work_log最近记录
            if os.path.exists(WORK_LOG):
                with open(WORK_LOG) as f:
                    lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    self.add_ok('WorkLog', f'最后记录: {last_line[:80]}')
                else:
                    self.add_fail('WorkLog', '日志为空')
            else:
                self.add_ok('WorkLog', '文件不存在（首次运行）')

            # 检查stats
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE) as f:
                    stats = json.load(f)
                self.add_ok('交易统计', f'总交易={stats.get("total_trades", 0)}, 连亏={stats.get("consecutive_losses", 0)}')
            else:
                self.add_ok('交易统计', '文件不存在（首次运行）')

            return True
        except Exception as e:
            self.add_fail('策略状态', f'检查失败: {e}', fix='重启任务进程')
            return False

    def check_log_size(self):
        """检查日志文件大小"""
        try:
            log_file = f'{TASK_DIR}/logs/auto_trade_20260417_224041.log'
            if os.path.exists(log_file):
                size = os.path.getsize(log_file)
                if size > 50 * 1024 * 1024:  # 50MB
                    self.add_fail('日志大小', f'{size/1024/1024:.1f}MB > 50MB', fix='轮转日志')
                    return False
                self.add_ok('日志大小', f'{size/1024:.1f}KB')
            return True
        except Exception as e:
            self.add_fail('日志检查', str(e))
            return False

    def auto_fix(self, fix_action):
        """执行自动修复"""
        try:
            if fix_action == '重启auto_trade.py':
                # 杀掉旧进程
                subprocess.run(['pkill', '-f', 'auto_trade.py'], capture_output=True)
                time.sleep(2)
                # 重启
                subprocess.Popen(
                    f'cd {TASK_DIR} && nohup python3 -u auto_trade.py > logs/auto_trade_$(date +%Y%m%d_%H%M%S).log 2>&1 &',
                    shell=True
                )
                return '已重启auto_trade.py'
            return None
        except Exception as e:
            return f'修复失败: {e}'

    def run(self):
        log('=' * 60)
        log('🔍 BTC合约任务自检开始')
        log('=' * 60)

        # 执行所有检查
        self.check_process()
        self.check_api_data()
        self.check_api_endpoints()
        self.check_strategy()
        self.check_log_size()

        # 生成报告
        report = {
            'time': self.timestamp,
            'checks_ok': self.checks_ok,
            'checks_fail': self.checks_fail,
            'items': self.results,
            'fixes': self.fixes
        }

        # 追加到检查日志
        logs = []
        if os.path.exists(CHECK_LOG):
            try:
                with open(CHECK_LOG) as f:
                    logs = json.load(f)
            except:
                logs = []
        logs.append(report)
        # 只保留最近100条
        logs = logs[-100:]
        with open(CHECK_LOG, 'w') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        # 写fix_log
        with open(FIX_LOG, 'a') as f:
            ts = self.timestamp
            for item in self.results:
                if item['status'] == '❌ FAIL':
                    f.write(f"[{ts}] ❌ {item['item']}: {item['detail']}\n")
                    if item.get('fix'):
                        f.write(f"[{ts}] 🔧 修复方案: {item['fix']}\n")

        # 发送微信通知（如果有问题）
        if self.checks_fail > 0:
            msg = f"🔴 自检发现问题({self.checks_fail}项)\n"
            for item in self.results:
                if item['status'] == '❌ FAIL':
                    msg += f"• {item['item']}: {item['detail']}\n"
            try:
                with open(NOTIFY_QUEUE, 'w') as f:
                    json.dump({'time': datetime.now().isoformat(), 'msg': msg, 'sent': False}, f)
            except:
                pass

        log('=' * 60)
        log(f'📊 自检完成: {self.checks_ok}项通过, {self.checks_fail}项失败')
        log('=' * 60)
        return report

if __name__ == '__main__':
    checker = HealthChecker()
    checker.run()
