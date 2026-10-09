import unittest
from property_timeline.email_signatures import strip_signature


class SignatureTests(unittest.TestCase):
    def test_insurance_signature(self):
        body = 'Premium increased.\n\nThank you,\nHave a great day!\n\nJessica M. Eye\nAccount Executive, Private Client | Gregory & Appel\np: 317.352.3374\nG&A Disclaimer'
        self.assertEqual(strip_signature(body), 'Premium increased.')

    def test_preserve_transaction_and_wire_instructions(self):
        body = 'File No.: 1054629\nBuyer: Sam\n\nRobyn Hammitt\nBranch Manager/Escrow Officer\nPhone: 317\n\n*Beware of cyber-crime!* Call to verify wiring instructions.\n\nThis message contains confidential information intended only for the recipient.\nRoutine disclaimer.'
        result = strip_signature(body)
        self.assertIn('File No.: 1054629', result)
        self.assertIn('Call to verify wiring instructions.', result)
        self.assertNotIn('Phone:', result)
        self.assertNotIn('Routine disclaimer', result)

    def test_contact_information_in_body_is_preserved(self):
        body = 'Contact Garrett today.\nPhone: 317-555-1234\nProperty Address: 5306 State Road 144\nThanks\nDarcy'
        self.assertEqual(strip_signature(body), body)

    def test_quoted_signature(self):
        self.assertEqual(strip_signature('> New substantive reply\n> Sent from my iPhone\n'), '> New substantive reply')

    def test_marketing_signature_preserves_price_terms(self):
        result = strip_signature('Pricing subject to change after 30 days\n\nSincerely,\n\nCustomer Service\nHope Plumbing, Heating and Cooling\nPromotional links')
        self.assertEqual(result, 'Pricing subject to change after 30 days')
