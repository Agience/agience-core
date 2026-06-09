import React from 'react'

const Privacy: React.FC = () => {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 text-gray-800">
      <p className="text-sm mb-4"><a href="/" className="text-indigo-600 underline">&lt;Home</a></p>
      <h2 className="text-3xl font-bold mb-6">Privacy Policy</h2>

      <p className="mb-4">
        Last updated: June 26, 2025
      </p>

      <p className="mb-4">
        At Ikailo Inc. ("we", "us"), we are committed to protecting your personal information. This policy outlines how we collect, use, and secure your data when you use our services relating to Agience and other related properties.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">1. Information We Collect</h3>
      <ul className="list-disc pl-6 mb-4 space-y-1">
        <li>Information you provide (e.g., email)</li>
        <li>Usage data for analytics</li>
        <li>Any data required for legal compliance</li>
      </ul>

      <h3 className="text-xl font-semibold mt-6 mb-2">2. Lawful Basis for Processing</h3>
      <p className="mb-4">We process data based on consent, legitimate interest, or legal obligation.</p>

      <h3 className="text-xl font-semibold mt-6 mb-2">3. How We Use Information</h3>
      <ul className="list-disc pl-6 mb-4 space-y-1">
        <li>To communicate and respond to inquiries</li>
        <li>To improve our platform and services</li>
        <li>To send optional newsletters or updates (opt-out anytime)</li>
      </ul>

      <h3 className="text-xl font-semibold mt-6 mb-2">4. Data Retention and Deletion</h3>
      <p className="mb-4">
        We retain personal data only as long as needed or required by law. You may request deletion at any time.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">5. Sharing Your Data</h3>
      <p className="mb-4">
        We may share data with trusted vendors (e.g., AWS, Mailchimp) or for legal compliance. No data is sold.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">6. Storage and Security</h3>
      <p className="mb-4">
        Data is stored securely with encryption and monitoring. Users are responsible for securing their own devices.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">7. Third-Party Links</h3>
      <p className="mb-4">
        We are not responsible for external websites. Review their privacy terms before use.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">8. Your Rights (Canada / PIPEDA)</h3>
      <ul className="list-disc pl-6 mb-4 space-y-1">
        <li>Access or correct your data</li>
        <li>Request deletion or portability</li>
        <li>Withdraw consent at any time</li>
        <li>Challenge compliance</li>
        <li>Object or restrict certain processing</li>
      </ul>

      <h3 className="text-xl font-semibold mt-6 mb-2">9. Legal Requests</h3>
      <p className="mb-4">
        We may disclose data if required by law, court order, or to protect legal rights.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">10. Children's Privacy</h3>
      <p className="mb-4">
        We do not knowingly collect data from children under 18. Contact us if you believe this has occurred.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">11. Opting Out</h3>
      <p className="mb-4">
        You can opt out of marketing emails or cookie tracking via browser settings and provided links.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">12. Governing Law</h3>
      <p className="mb-4">
        Governed by Ontario law. Disputes are subject to the Terms of Use jurisdiction.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">13. Contact</h3>      
      <p className="mt-2">        
        Ikailo Inc.<br />
        50 Richmond St. E Ste 119 Firm #2048<br />
        Oshawa, ON L1G 7C7<br /><br/>
        <a href="mailto:connect@agience.ai" className="text-indigo-600 underline">connect@agience.ai</a>
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2 mt-6">14. Updates</h3>
      <p className="mb-4">
        This Privacy Policy may be updated. Continued use after updates implies acceptance. Check this page regularly for changes.
      </p>      
    </div>
  )
}

export default Privacy
