import unittest

from ava_py.browser import allowed_url, course_links, match_wl_to_ava, section_urls
from ava_py.rules import activity_identity, completion_status, is_wl_course, quiz_view_status


class SelectionRulesTest(unittest.TestCase):
    def test_only_wl_courses(self):
        self.assertTrue(is_wl_course("Engenharia de Software (WL)"))
        self.assertTrue(is_wl_course("Métodos Numéricos (wl) - 2026"))
        self.assertFalse(is_wl_course("Engenharia de Software"))
        self.assertTrue(is_wl_course("Engenharia de Software WL"))

    def test_activity_titles_and_units(self):
        self.assertEqual(activity_identity("U1 - Atividade de Aprendizagem"), (1, "Atividade de Aprendizagem"))
        self.assertEqual(activity_identity("Avaliação da Unidade", "Unidade 4"), (4, "Avaliação da Unidade"))
        self.assertIsNone(activity_identity("U5 - Atividade de Aprendizagem"))
        self.assertIsNone(activity_identity("U2 - Trabalho: Avaliação da Unidade"))
        self.assertIsNone(activity_identity("U1 - Material de Aula"))

    def test_completion_requires_positive_marker(self):
        self.assertEqual(completion_status(["Concluído"]), "concluída")
        self.assertEqual(completion_status(["completion-auto-y"]), "concluída")
        self.assertEqual(completion_status(["Não concluído"]), "verificar no portal")
        self.assertEqual(completion_status([]), "verificar no portal")

    def test_only_known_ava_pages(self):
        self.assertTrue(allowed_url("https://www.avaeduc.com.br/mod/quiz/view.php?id=123"))
        self.assertTrue(allowed_url("https://www.avaeduc.com.br/course/view.php?id=5", course=True))
        self.assertFalse(allowed_url("https://example.com/mod/quiz/view.php?id=123"))
        self.assertFalse(allowed_url("https://www.avaeduc.com.br/mod/quiz/attempt.php?id=123"))

    def test_course_name_can_come_from_course_card(self):
        class FakeLocator:
            def evaluate_all(self, _script):
                return [
                    {"name": "Abrir curso", "cardName": "Engenharia de Software (WL)",
                     "url": "https://www.avaeduc.com.br/course/view.php?id=5"},
                    {"name": "Outro curso", "cardName": "Matéria regular",
                     "url": "https://www.avaeduc.com.br/course/view.php?id=6"},
                ]

        class FakePage:
            def locator(self, _selector):
                return FakeLocator()

        self.assertEqual(
            course_links(FakePage()),
            [("Engenharia de Software (WL)", "https://www.avaeduc.com.br/course/view.php?id=5")],
        )

    def test_wl_portal_names_match_only_their_ava_courses(self):
        matches, unresolved = match_wl_to_ava(
            ["Métodos Numéricos Aplicados", "Engenharia de Software"],
            [
                ("Metodos Numericos Aplicados", "https://www.avaeduc.com.br/course/view.php?id=1"),
                ("Competências para a Vida", "https://www.avaeduc.com.br/course/view.php?id=2"),
            ],
        )
        self.assertEqual(matches, [("Metodos Numericos Aplicados", "https://www.avaeduc.com.br/course/view.php?id=1")])
        self.assertEqual(unresolved, ["Engenharia de Software"])

    def test_scans_unit_section_urls(self):
        class FakeLocator:
            def evaluate_all(self, _script):
                return [
                    {"url": "https://www.avaeduc.com.br/course/view.php?id=5&topic=20",
                     "text": "Avançar para Unidade de Ensino 2"},
                    {"url": "https://www.avaeduc.com.br/course/view.php?id=5&topic=50",
                     "text": "Avançar para Unidade de Ensino 5"},
                ]

        class FakePage:
            def locator(self, _selector):
                return FakeLocator()

        urls = section_urls(FakePage(), "https://www.avaeduc.com.br/course/view.php?id=5")
        self.assertEqual(urls, ["https://www.avaeduc.com.br/course/view.php?id=5&topic=20"])

    def test_quiz_view_status_prioritizes_submitted_attempt(self):
        table = {"headers": ["Tentativa", "Estado", "Nota / 10,00", "Revisão"],
                 "rows": [["1", "Finalizada Enviada(s) segunda", "3,00", "Revisão"],
                          ["2", "Em progresso", "", ""]]}
        self.assertEqual(quiz_view_status([table], ["Fazer uma outra tentativa"]), ("concluída", "3,00"))

    def test_quiz_view_status_in_progress_and_pending(self):
        table = {"headers": ["Tentativa", "Estado", "Revisão"],
                 "rows": [["1", "Em progresso", ""]]}
        self.assertEqual(quiz_view_status([table], ["Continuar a última tentativa"]), ("em andamento", ""))
        self.assertEqual(quiz_view_status([], ["Tentar responder o questionário agora"]), ("pendente", ""))
        self.assertEqual(quiz_view_status([], ["Fazer uma outra tentativa"]), ("verificar no portal", ""))


if __name__ == "__main__":
    unittest.main()
