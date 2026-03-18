import requests
import json
import csv
import time
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

# 全局锁
csv_lock = Lock()


def resolve_b23_short_url(url):
    """解析b23.tv短链接，获取真实的B站视频链接"""
    try:
        resp = requests.head(url, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True, timeout=5)
        real_url = resp.url
        return real_url
    except:
        return None


def extract_bvid(url):
    """从B站链接中提取BV号（支持短链接自动解析）"""
    if "b23.tv" in url:
        url = resolve_b23_short_url(url)
        if not url:
            return None

    pattern = r'BV([A-Za-z0-9]{10})'
    match = re.search(pattern, url)
    if match:
        return "BV" + match.group(1)
    return None


def get_sessdata_from_cookie(cookie_str):
    """从完整cookie中提取 SESSDATA"""
    match = re.search(r'SESSDATA=([^;]+)', cookie_str)
    if match:
        return match.group(1).strip()
    return None


def get_bilibili_comments(
        oid,
        type_code,
        sessdata=None,
        sort=0,
        nohot=0,
        ps=20,
        max_pages=100,
        delay=1,
        append_mode=False
):
    url = "https://api.bilibili.com/x/v2/reply"
    params = {
        "type": type_code,
        "oid": oid,
        "sort": sort,
        "nohot": nohot,
        "ps": ps,
        "pn": 1
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bilibili.com/",
        "Cookie": f"SESSDATA={sessdata};"
    }

    with csv_lock:
        mode = 'a' if append_mode else 'w'
        with open('b站评论.csv', mode, newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['视频BV号', '评论ID', '用户名', '点赞数', '回复数', '内容', '发布时间']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not append_mode:
                writer.writeheader()

            page = 1
            while True:
                if page > max_pages:
                    print(f"视频 {oid} 已达最大页数，停止")
                    break
                print(f"正在获取 {oid} 第 {page} 页评论...")
                params["pn"] = page

                try:
                    response = requests.get(url, params=params, headers=headers, timeout=10)
                    response.raise_for_status()
                except Exception as e:
                    print(f"请求失败：{e}")
                    break

                try:
                    data = response.json()
                except:
                    print("JSON解析失败")
                    break

                if data.get("code") != 0:
                    print(f"接口错误：{data.get('message')}")
                    break

                replies = data.get("data", {}).get("replies", [])
                if not replies:
                    print(f"无更多评论")
                    break

                for comment in replies:
                    rpid = comment.get("rpid", "")
                    uname = comment.get("member", {}).get("uname", "匿名")
                    like = comment.get("like", 0)
                    rcount = comment.get("rcount", 0)
                    message = comment.get("content", {}).get("message", "").replace("\n", " ").replace("\r", "")
                    ctime = comment.get("ctime", 0)
                    try:
                        publish_time = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        publish_time = "未知"

                    writer.writerow({
                        "视频BV号": oid,
                        "评论ID": rpid,
                        "用户名": uname,
                        "点赞数": like,
                        "回复数": rcount,
                        "内容": message,
                        "发布时间": publish_time
                    })

                page += 1
                time.sleep(delay)


def process_video(url, sessdata, append_mode=True):
    bvid = extract_bvid(url)
    if not bvid:
        print(f"无法提取BV号：{url}")
        return False

    print(f"\n===== 开始爬取：{bvid} =====")
    try:
        get_bilibili_comments(
            oid=bvid,
            type_code=1,
            sessdata=sessdata,
            sort=1,
            max_pages=100,
            delay=1,
            append_mode=append_mode
        )
        return True
    except Exception as e:
        print(f"爬取失败：{e}")
        return False


if __name__ == "__main__":
    MAX_WORKERS = 3

    # ===================== 核心：读取 bilicookie.txt =====================
    try:
        with open("bilicookie.txt", "r", encoding="utf-8") as f:
            cookie_content = f.read().strip()

        SESSDATA = get_sessdata_from_cookie(cookie_content)
        if not SESSDATA:
            print("❌ 未能从文件中提取到 SESSDATA")
            exit()
        print("✅ 成功读取 bilicookie.txt 并提取 SESSDATA")
    except Exception as e:
        print(f"❌ 读取 bilicookie.txt 失败：{e}")
        exit()

    # 你要爬的5个视频
    target_urls = [
        "https://b23.tv/vFRMaBL?share_medium=android&share_source=weixin&bbid=XU84C0B897EDE2473469EEED32CCD26CCF9D5&ts=1773824372516",
        "https://b23.tv/KsI4qWm?share_medium=android&share_source=weixin&bbid=XU84C0B897EDE2473469EEED32CCD26CCF9D5&ts=1773824427890",
        "https://b23.tv/OUczg2e?share_medium=android&share_source=weixin&bbid=XU84C0B897EDE2473469EEED32CCD26CCF9D5&ts=1773824484540",
        "https://b23.tv/prgLIyq?share_medium=android&share_source=weixin&bbid=XU84C0B897EDE2473469EEED32CCD26CCF9D5&ts=1773824503713",
        "https://b23.tv/MnKRyau?share_medium=android&share_source=weixin&bbid=XU84C0B897EDE2473469EEED32CCD26CCF9D5&ts=1773824529559"
    ]

    # 初始化CSV
    with open('b站评论.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['视频BV号', '评论ID', '用户名', '点赞数', '回复数', '内容', '发布时间'])
        writer.writeheader()

    print(f"\n开始爬取 {len(target_urls)} 个B站视频评论\n")

    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        tasks = {executor.submit(process_video, url, SESSDATA): url for url in target_urls}
        success = 0
        fail = 0

        for future in as_completed(tasks):
            try:
                if future.result():
                    success += 1
                else:
                    fail += 1
            except:
                fail += 1

    print("\n==================== 爬取完成 ====================")
    print(f"总计：{len(target_urls)} | 成功：{success} | 失败：{fail}")
    print(f"文件保存位置：{os.path.abspath('b站评论.csv')}")