from analyzer import _eh_erro_transitorio


class _DeadlineExceededFake(Exception):
    pass


def test_erro_transitorio_cobre_codigos_e_deadline():
    assert _eh_erro_transitorio(RuntimeError("500 INTERNAL")) is True
    assert _eh_erro_transitorio(RuntimeError("503 UNAVAILABLE")) is True
    assert _eh_erro_transitorio(_DeadlineExceededFake("504 Deadline Exceeded")) is True
    assert _eh_erro_transitorio(RuntimeError("429 RESOURCE_EXHAUSTED")) is True


def test_quota_diaria_bloqueia_retry_e_erro_400_nao_e_transitorio():
    assert _eh_erro_transitorio(RuntimeError("429 RESOURCE_EXHAUSTED"), quota_diaria=True) is False
    assert _eh_erro_transitorio(RuntimeError("503 UNAVAILABLE"), quota_diaria=True) is False
    assert _eh_erro_transitorio(ValueError("400 INVALID_ARGUMENT"), quota_diaria=False) is False