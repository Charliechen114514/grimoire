"""Tests for section_splitter — Chinese/English chapter number parsing and TOC matching."""

import pytest

from src.section_splitter import (
    _cn_to_int,
    _collect_toc_subtree,
    _parse_chapter_number,
    split_chapter_into_sections,
)


# ── _cn_to_int ──

@pytest.mark.parametrize("cn, expected", [
    ("一", 1),
    ("二", 2),
    ("三", 3),
    ("四", 4),
    ("五", 5),
    ("六", 6),
    ("七", 7),
    ("八", 8),
    ("九", 9),
    ("十", 10),
    ("十一", 11),
    ("十九", 19),
    ("二十", 20),
    ("二十一", 21),
    ("四十五", 45),
    ("七十六", 76),
    ("九十九", 99),
])
def test_cn_to_int_valid(cn, expected):
    assert _cn_to_int(cn) == expected


@pytest.mark.parametrize("s, expected", [
    ("1", 1),
    ("5", 5),
    ("42", 42),
    ("", None),
    ("abc", None),
    ("百", None),
])
def test_cn_to_int_misc(s, expected):
    assert _cn_to_int(s) == expected


# ── _parse_chapter_number ──

@pytest.mark.parametrize("title, expected", [
    ("Chapter 1", 1),
    ("Chapter 42", 42),
    ("chapter 7", 7),
    ("第一章 Ubuntu 系统安装", 1),
    ("第五章 I.MX6U-ALPHA/Mini 开发平台介绍", 5),
    ("第十章 C 语言版LED 灯实验", 10),
    ("第二十一章  UART 串口通信实验", 21),
    ("第四十五章 pinctrl和gpio子系统实验", 45),
    ("第七十六章 Linux ADC 驱动实验", 76),
    ("第1章 测试", 1),
    ("第20章 测试", 20),
])
def test_parse_chapter_number_valid(title, expected):
    assert _parse_chapter_number(title) == expected


@pytest.mark.parametrize("title", [
    "第一篇 Ubuntu系统入门篇",
    "附录A 其他根文件系统构建",
    "前言",
    "ALPHA/Mini开发板教程适配表",
    "I.MX6U 嵌入式Linux 驱动开发指南",
    "",
])
def test_parse_chapter_number_non_chapter(title):
    assert _parse_chapter_number(title) is None


# ── _collect_toc_subtree ──

def _make_toc() -> list[tuple[int, str, int]]:
    """模拟 driver_imx6ull 的 TOC 结构。"""
    return [
        (1, "ALPHA/Mini开发板教程适配表", 1),
        (1, "前言", 3),
        (1, "第一篇 Ubuntu系统入门篇", 5),
        (1, "第一章 Ubuntu系统安装", 6),
        (2, "1.1 安装虚拟机软件VMware", 6),
        (2, "1.2 创建虚拟机", 10),
        (2, "1.3 安装Ubuntu操作系统", 15),
        (3, "1.3.1 获取Ubuntu系统", 15),
        (3, "1.3.2 安装Ubuntu操作系统", 18),
        (1, "第二章 Ubuntu系统入门", 22),
        (2, "2.1 Ubuntu系统初体验", 22),
        (2, "2.2 Ubuntu终端操作", 28),
        (2, "2.3 Shell操作", 32),
        (1, "第二篇 裸机开发篇", 40),
        (1, "第四章 开发环境搭建", 42),
        (2, "4.1 Ubuntu和Windows文件互传", 42),
        (2, "4.2 Ubuntu下NFS和SSH服务开启", 48),
        (1, "第十七章 GPIO中断实验", 200),
        (2, "17.1 Cortex-A7中断系统简介", 200),
        (2, "17.2 硬件原理分析", 210),
        (2, "17.3 实验程序编写", 220),
        (2, "17.4 编译下载验证", 230),
        (1, "附录A 其他根文件系统构建", 1886),
        (2, "第A1章 Buildroot根文件系统构建", 1886),
    ]


def test_collect_toc_subtree_chinese_ch1():
    toc = _make_toc()
    subtree = _collect_toc_subtree(toc, 1)
    assert len(subtree) == 5
    assert subtree[0] == (2, "1.1 安装虚拟机软件VMware", 6)
    assert subtree[1] == (2, "1.2 创建虚拟机", 10)


def test_collect_toc_subtree_chinese_ch2():
    toc = _make_toc()
    subtree = _collect_toc_subtree(toc, 2)
    assert len(subtree) == 3
    assert subtree[0] == (2, "2.1 Ubuntu系统初体验", 22)


def test_collect_toc_subtree_chinese_ch17():
    toc = _make_toc()
    subtree = _collect_toc_subtree(toc, 17)
    assert len(subtree) == 4
    assert subtree[0] == (2, "17.1 Cortex-A7中断系统简介", 200)


def test_collect_toc_subtree_chinese_ch4():
    toc = _make_toc()
    subtree = _collect_toc_subtree(toc, 4)
    assert len(subtree) == 2
    assert subtree[0] == (2, "4.1 Ubuntu和Windows文件互传", 42)


def test_collect_toc_subtree_not_found():
    toc = _make_toc()
    subtree = _collect_toc_subtree(toc, 99)
    assert subtree == []


def test_collect_toc_subtree_english():
    """英文 TOC 仍然正常工作。"""
    toc = [
        (1, "Chapter 1: Introduction", 1),
        (2, "1.1 Overview", 1),
        (2, "1.2 Setup", 5),
        (1, "Chapter 2: Basics", 10),
        (2, "2.1 Fundamentals", 10),
    ]
    subtree = _collect_toc_subtree(toc, 1)
    assert len(subtree) == 2
    subtree = _collect_toc_subtree(toc, 2)
    assert len(subtree) == 1
