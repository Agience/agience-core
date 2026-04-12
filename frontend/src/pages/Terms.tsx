import React from 'react'

const Terms: React.FC = () => {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 text-gray-800">
      <p className="text-sm mb-4"><a href="/" className="text-indigo-600 underline">&lt;Home</a></p>
      <h2 className="text-3xl font-bold mb-6">Terms of Use</h2>

      <p className="mb-4">
        Welcome to Agience and other services operated by Ikailo Inc. By using our site, you agree to these Terms of Use. If you do not agree, please do not use the site.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">1. Acceptance of Terms</h3>
      <p className="mb-4">
        By accessing or using our site, you confirm that you are legally competent and have read, understood, and agreed to these Terms and our Privacy and Cookie Policies.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">2. Allowed Use</h3>
      <ul className="list-disc pl-6 mb-4 space-y-1">
        <li>Learning about Agience and its services</li>
        <li>Contacting us via provided methods</li>
        <li>Personal, non-commercial usage</li>
      </ul>

      <h3 className="text-xl font-semibold mt-6 mb-2">3. Prohibited Uses</h3>
      <ul className="list-disc pl-6 mb-4 space-y-1">
        <li>Unauthorized access or data scraping</li>
        <li>Violation of intellectual property rights</li>
        <li>Misuse of content or information</li>
        <li>Unlawful activities</li>
      </ul>

      <h3 className="text-xl font-semibold mt-6 mb-2">4. Ownership</h3>
      <p className="mb-4">
        All site content is owned by Ikailo Inc. You may not copy, modify, or distribute content without our written permission.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">5. Privacy</h3>
      <p className="mb-4">
        Please refer to our <a href="/privacy" className="text-indigo-600 underline">Privacy Policy</a> for details on data collection and usage.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">6. Third-Party Links</h3>
      <p className="mb-4">
        We are not responsible for content or privacy practices of third-party sites linked from ours. Use them at your own risk.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">7. Disclaimer</h3>
      <p className="mb-4">
        Content on our site is provided "as-is" and may not be accurate, complete, or current. We disclaim liability to the fullest extent permitted by law.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">8. Limitation of Liability</h3>
      <p className="mb-4">
        We are not liable for any damages, direct or indirect, arising from your use of the site. Your sole remedy is to discontinue use.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">9. Legal Action</h3>
      <p className="mb-4">
        Malicious actions against Agience.ai or Ikailo Inc. may result in legal action.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">10. Indemnification</h3>
      <p className="mb-4">
        You agree to indemnify Ikailo Inc. against claims arising from your use of the site or violation of these Terms.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">11. Governing Law</h3>
      <p className="mb-4">
        These Terms are governed by Ontario, Canada law. Disputes must first attempt to be resolved through good-faith negotiation.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">12. Notices</h3>
      <p className="mb-4">
        You consent to receive communications electronically. We may notify you via email or by posting notices on our website.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">13. General Terms</h3>
      <ul className="list-disc pl-6 mb-4 space-y-1">
        <li>Severability: Invalid terms do not affect the rest.</li>
        <li>Waiver: Failure to enforce is not a waiver.</li>
        <li>Entire Agreement: Terms, Privacy Policy, and Cookie Policy form the full agreement.</li>
        <li>Updates: Terms may be updated without notice; continued use means acceptance.</li>
      </ul>

      <h3 className="text-xl font-semibold mt-6 mb-2">14. Contact</h3>      
      <p className="mt-2">        
        Ikailo Inc.<br />
        50 Richmond St. E Ste 119 Firm #2048<br />
        Oshawa, ON L1G 7C7<br /><br/>
        <a href="mailto:connect@agience.ai" className="text-indigo-600 underline">connect@agience.ai</a>
      </p>      
    </div>
  )
}

export default Terms
