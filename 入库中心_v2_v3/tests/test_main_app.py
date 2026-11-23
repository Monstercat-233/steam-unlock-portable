def test_format_judge_string_tuple():
    from main_app import format_judge
    s = format_judge((True, "需票据/补丁", "单机无需", "有 Denuvo"))
    assert "下载" in s and "运行" in s and "联机" in s


def test_account_label():
    from main_app import account_label
    assert "monstercaatt" in account_label({"account_name": "monstercaatt", "accountid": 1230565209})
