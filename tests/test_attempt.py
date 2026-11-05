import unittest

from playwright.sync_api import sync_playwright

from ava_py.answer_validation import CannotAnswer, validate_decision
from ava_py.attempt import extract_question, first_attempt_url, summary_rows, verify_summary


class AttemptTest(unittest.TestCase):
    def test_resume_starts_from_first_question_of_same_attempt(self):
        self.assertEqual(
            first_attempt_url("https://www.avaeduc.com.br/mod/quiz/attempt.php?attempt=3717143&page=9"),
            "https://www.avaeduc.com.br/mod/quiz/attempt.php?attempt=3717143",
        )
        with self.assertRaises(CannotAnswer):
            first_attempt_url("https://example.com/mod/quiz/attempt.php?attempt=3717143")

    def test_reads_question_and_choices_by_current_content(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content('''
                  <div class="que"><h3>Questão 3</h3>
                    <div class="formulation"><div class="qtext">Quanto é 2 + 2?</div>
                      <div class="answer">
                        <div class="r0"><input type="radio" id="x1" name="q3"><label for="x1">a. 5</label></div>
                        <div class="r1"><input type="radio" id="x2" name="q3"><label for="x2">b. 4</label></div>
                      </div>
                    </div>
                  </div>''')
                question = extract_question(page.locator(".que"))
                self.assertEqual(question["stem"], "Quanto é 2 + 2?")
                self.assertEqual([option["text"] for option in question["options"]], ["5", "4"])
                decision = validate_decision({
                    "answerable": True, "choice_index": 2, "choice_text": "4",
                    "explanation": "Dois somados a dois resultam em quatro unidades.",
                }, ["5", "4"])
                page.locator('input[type="radio"]').nth(decision.index).check()
                self.assertTrue(page.locator("#x2").is_checked())
                with self.assertRaises(CannotAnswer):
                    validate_decision({
                        "answerable": True, "choice_index": 2, "choice_text": "5",
                        "explanation": "Dois somados a dois resultam em quatro unidades.",
                    }, ["5", "4"])
                page.set_content('''<div class="que"><h3>Questão 1</h3><div class="formulation">
                    <div class="qtext">Calcule <img alt="O de n ao quadrado" src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="></div>
                    <div class="answer"><input type="radio" id="f" name="q"><label for="f">a. <img alt="O de n ao quadrado" src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="></label></div>
                    </div></div>''')
                rich_question = extract_question(page.locator(".que"))
                self.assertIn("O de n ao quadrado", rich_question["stem"])
                self.assertIn("O de n ao quadrado", rich_question["options"][0]["text"])
            finally:
                browser.close()

    def test_summary_blocks_blank_question(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content('''<table><thead><tr><th>Pergunta</th><th>Status</th></tr></thead>
                    <tbody><tr><td>1</td><td>Resposta salva</td></tr>
                    <tr><td>2</td><td>Ainda não respondida</td></tr></tbody></table>''')
                with self.assertRaises(CannotAnswer):
                    verify_summary(summary_rows(page))
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
