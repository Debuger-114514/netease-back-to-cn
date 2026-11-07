# 网易云音乐客户端回国脚本

让网易云音乐 PC 客户端在海外也能正常播放版权歌曲。装好就不用管了。

---

## 它解决什么

海外用网易云音乐，大量歌曲是灰色的。

常见做法是装个浏览器插件 → 打开网页版 → 登录 → 播一首歌，然后客户端也会跟着解锁。但每过一段时间就要重复一遍，很麻烦。

这个脚本把那套动作自动化了：从你已经登录的客户端里取出凭据，定时用后台浏览器带伪 IP 访问一遍，把账号的国内授权续上。你不需要开浏览器，也不需要重新登录。

---

## 前提

- Windows（凭据解密依赖 Windows 的 DPAPI，其他系统用不了）
- 网易云音乐 PC 客户端**已经登录**——脚本从客户端里取凭据，所以不用你再登一次
- Python 3.8+

---

## 安装

### 双击安装（推荐）

1. 本页右上角 **Code → Download ZIP**
2. 解压到任意目录（路径里别带空格和中文，省得踩坑）
3. 双击 **`一键安装.bat`**
4. 看到「安装完成」就好了

安装器会自动检查 Python、装依赖、注册定时任务，并立即刷新一次。之后每 6 小时自动跑，全程无窗口。

**卸载**：双击 `卸载.bat`。

### 或者用命令行

```powershell
git clone https://github.com/Debuger-114514/netease-back-to-cn.git
cd netease-back-to-cn
pip install -r requirements.txt
pwsh -File install_task.ps1
```

---

## 确认它在工作

```powershell
schtasks /Run /TN NetEaseRefresh
```

等一两分钟，看 `logs\run.log`，出现「结论：正常」就说明跑通了。

想直接看每一步的输出，双击 `手动刷新一次.bat`。

---

## 常见问题

**提示 `AuthorizationManager 检查失败`**

PowerShell 执行策略拦了。换个写法：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\install_task.ps1'"
```

**日志里的中文是乱码**

文件本身是 UTF-8，只是终端显示问题。用记事本打开，或者：

```powershell
Get-Content logs\run.log -Encoding utf8
```

**歌还是灰的**

1. 确认客户端处于登录状态
2. 这首歌可能本身就没版权（比如周杰伦全系列），和地区限制无关，怎么刷都没用
3. 重启一次客户端——它在授权失效期间可能缓存了不可播状态

**卸载**

```powershell
pwsh -File install_task.ps1 -Remove
```

---

## 原理简述

网易云的地区判定挂在**账号**上，不挂在连接上。

网页版带着 `X-Real-IP: 211.161.244.70` 访问时，服务端会按国内处理，并把这份授权记到账号上；客户端用同一份 cookie 请求，就共享到了这份授权。

实测证据：同一个账号、同一份 cookie，只切换这一个请求头，`weapi/cdns` 返回的 CDN 节点清单完全不同（带伪 IP 时出现 `m3`，不带时出现 `sv1/sv2`）。

所以脚本只做三件事：

1. 从客户端的 CEF Cookie 库里解出 `MUSIC_U`（DPAPI + AES-256-GCM）
2. 用无头 Edge 注入这份 cookie 和伪 IP 头，访问一遍音乐页并发起播放
3. 抽 20 首热歌榜的歌曲体检，可播率低于 85% 就在桌面留一个告警文件

凭据保存在 `%APPDATA%\ne-refresh\`，与浏览器完全隔离，清理 Edge 的浏览数据不会影响它。

---

## 已知限制

- 仅支持 Windows
- 网页版播放接口本身会返回 `参数错误`，这是网易云自己关闭了网页播放，不影响刷新
- 授权能维持多久尚未测出（目前连续 12 轮可播率都是 100%），每 6 小时的间隔偏保守

---

## 声明

仅供个人学习与网络行为研究，使用者自行承担账号风险。本项目不提供任何账号、token 或在线服务。

## License

MIT
