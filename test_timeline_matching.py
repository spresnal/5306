import unittest
from datetime import datetime
from timeline_html import prior_quote, quoted_identity, email_body_html
from timeline_pdf_readability import collapse_repeated_quotes


class QuoteMatchingTests(unittest.TestCase):
    def setUp(self):
        self.body = 'Good morning Garrett-\n\nDo you have an update this morning?\nThanks\nDarcy'
        self.earlier = dict(id='gmail:0163', text=' '.join(self.body.split()),
                            opening=' '.join(self.body.split()), sender='darcy@truebloodre.com', sender_name='darcy knott',
                            minute=datetime(2026, 8, 5, 9, 54))
        self.header = 'From: Darcy Knott <darcy@truebloodre.com>\nSent: Wednesday, August 5, 2026 9:54 AM\nSubject: Re: Title Work\n\n'

    def test_short_outlook_reply(self):
        self.assertEqual(prior_quote(self.header + self.body, [self.earlier]), 'gmail:0163')

    def test_short_gmail_reply(self):
        header = 'On Wed, Aug 5, 2026 at 9:54\u202fAM Darcy Knott <darcy@truebloodre.com>\nwrote:\n\n'
        self.assertEqual(prior_quote(header + self.body, [self.earlier]), 'gmail:0163')

    def test_gmail_mobile_comma_date_and_nested_quotes(self):
        body = 'Sarah sent her venmo information.\n\nThanks,\nDerrick'
        earlier = dict(id='gmail:0218', text=' '.join(body.split()),
                       opening=' '.join(body.split()), sender='derrickhasenour@gmail.com',
                       sender_name='derrick hasenour', minute=datetime(2026, 8, 8, 18, 23))
        for depth in range(4):
            with self.subTest(depth=depth):
                prefix = '> ' * depth
                header = (prefix + 'On Sat, Aug 8, 2026, 6:23\u202fPM Derrick Hasenour '
                          '<derrickhasenour@gmail.com>\n' + prefix + 'wrote:\n\n')
                quotation = header + '\n'.join('> ' + prefix + line if line else ''
                                               for line in body.splitlines())
                self.assertEqual(quoted_identity(quotation)[1], earlier['minute'])
                self.assertEqual(prior_quote(quotation, [earlier]), 'gmail:0218')
                html = email_body_html('Reply\n\n' + quotation, 'Sam', earlier_email_text=[earlier])
                self.assertIn('data-prior="gmail:0218"', html)
                pdf_html = collapse_repeated_quotes(html)
                self.assertIn('Repeated quotation shown in', pdf_html)
                self.assertNotIn('Sarah sent her venmo information.', pdf_html)
                self.assertIsNone(prior_quote(quotation.replace('6:23', '6:26'), [earlier]))
                self.assertIsNone(prior_quote(quotation.replace('venmo', 'bank'), [earlier]))

    def test_short_requires_identity(self):
        for header in ('', self.header.replace('9:54', '9:56'),
                       self.header.replace('darcy@truebloodre.com', 'other@example.com')):
            self.assertIsNone(prior_quote(header + self.body, [self.earlier]))

    def test_one_minute_header_difference(self):
        self.assertEqual(prior_quote(self.header.replace('9:54', '9:55') + self.body, [self.earlier]), 'gmail:0163')

    def test_outlook_nested_mailto(self):
        header = 'On Wed, Aug 5, 2026 at 9:54 AM Darcy Knott <darcy@truebloodre.com<mailto:darcy@truebloodre.com>> wrote:\n\n'
        self.assertEqual(prior_quote(header + self.body, [self.earlier]), 'gmail:0163')

    def test_full_display_name_without_address(self):
        header = self.header.replace('Darcy Knott <darcy@truebloodre.com>', 'Darcy Knott')
        self.assertEqual(prior_quote(header + self.body, [self.earlier]), 'gmail:0163')
        self.assertIsNone(prior_quote(header.replace('Darcy Knott', 'Darcy') + self.body, [self.earlier]))
        other = dict(self.earlier, sender='another@example.com', id='gmail:9999')
        self.assertIsNone(prior_quote(header + self.body, [self.earlier, other]))

    def test_meridiem_is_preserved(self):
        for time, hour in [('1:13 PM', 13), ('12:51 PM', 12), ('12:51 AM', 0), ('9:54 PM', 21)]:
            header = f'On Wed, Aug 5, 2026 at {time} Darcy Knott <darcy@truebloodre.com> wrote:\n\nText'
            self.assertEqual(quoted_identity(header)[1].hour, hour)

    def test_short_requires_complete_opening(self):
        self.assertIsNone(prior_quote(self.header + 'Thanks\nDarcy', [self.earlier]))

    def test_changed_text_stays_visible(self):
        self.assertIsNone(prior_quote(self.header + self.body.replace('morning?', 'afternoon?'), [self.earlier]))

    def test_long_match_requires_complete_passage_and_identity(self):
        text = 'word ' * 20 + 'end'
        self.earlier['text'] = 'prefix' + text
        self.assertIsNone(prior_quote(text, [self.earlier]))
        self.earlier['text'] = 'prefix ' + text
        self.assertIsNone(prior_quote(text, [self.earlier]))
        self.earlier['opening'] = text.strip()
        self.assertEqual(prior_quote(self.header + text, [self.earlier]), 'gmail:0163')
        self.assertIsNone(prior_quote(self.header.replace('darcy@truebloodre.com', 'other@example.com') + text, [self.earlier]))

    def test_conflicting_explicit_headers_stay_visible(self):
        self.earlier['fields'] = {'Subject': 'Title Work', 'To': 'Sam <sam@example.com>', 'Cc': ''}
        self.assertIsNone(prior_quote(self.header.replace('Title Work', 'New Offer') + self.body, [self.earlier]))
        self.assertIsNone(prior_quote(self.header + 'To: Other <other@example.com>\n\n' + self.body, [self.earlier]))

    def test_matching_nested_passage_uses_its_own_time(self):
        nested = dict(text=self.earlier['opening'], sender=self.earlier['sender'], minute=self.earlier['minute'], fields={})
        self.earlier['passages'] = [nested]
        self.earlier['minute'] = datetime(2026, 8, 6, 11, 30)
        html = email_body_html('New reply\n\n' + self.header + self.body, 'Sam', earlier_email_text=[self.earlier])
        self.assertIn('data-prior="gmail:0163"', html)
        self.assertNotIn('Quoted time differs', html)


if __name__ == '__main__':
    unittest.main()
