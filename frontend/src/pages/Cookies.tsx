import React from 'react';

const Cookies: React.FC = () => {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 text-gray-800">
      <p className="text-sm mb-4">
        <a href="/" className="text-indigo-600 underline">&lt;Home</a>
      </p>

      <h2 className="text-3xl font-bold mb-6">Cookie Policy</h2>
      <p className="mb-4">Last updated: June 26, 2025</p>

      <p className="mb-4">
        This Cookie Policy describes how cookies are used on <span className="text-indigo-600 underline ml-1">https://*.agience.ai/</span> and related web or mobile properties ("Site"). By using the Site, you agree we may store and access cookies as described here.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">What Are Cookies?</h3>
      <p className="mb-4">
        Cookies are small text files placed on your device when you visit a website. They store information like preferences or site activity to enhance your experience.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">What Are Cookies Used For?</h3>
      <p className="mb-4">
        Cookies help us understand how the Site is used, support navigation, remember user settings, and improve overall experience. They may also make marketing more relevant to you.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">Types of Cookies We Use</h3>
      <ul className="list-disc pl-6 mb-4 space-y-2">
        <li>
          <strong>Essential:</strong> Required for the Site to function properly, such as maintaining session state and user preferences.
        </li>
        <li>
          <strong>Functional:</strong> Remember your preferences and settings to enhance usability.
        </li>
        <li>
          <strong>Analytics:</strong> Help us understand user behavior and improve our services.
        </li>
      </ul>

      <h3 className="text-xl font-semibold mt-6 mb-2">Cookie Duration</h3>
      <p className="mb-4">
        Session cookies are temporary and deleted when your browser closes. Persistent cookies remain until they expire or are manually deleted.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">Managing Cookies</h3>
      <p className="mb-2">You can manage cookies through your browser settings:</p>
      <ul className="list-disc pl-6 space-y-1 mb-4">
        <li><strong>Chrome:</strong> Settings &gt; Privacy & Security &gt; Cookies and other site data</li>
        <li><strong>Firefox:</strong> Options &gt; Privacy & Security &gt; Cookies and Site Data</li>
        <li><strong>Safari:</strong> Preferences &gt; Privacy &gt; Manage Website Data</li>
        <li><strong>Edge:</strong> Settings &gt; Cookies and site permissions</li>
      </ul>
      <p className="mb-4">
        Blocking cookies may impact some functionality. Refer to your browser's documentation for more guidance.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">Changes to This Policy</h3>
      <p className="mb-4">
        We may update this Cookie Policy to reflect changes in technology, law, or our practices. Check this page periodically. Continued use of the Site indicates acceptance of any changes.
      </p>

      <h3 className="text-xl font-semibold mt-6 mb-2">Contact</h3>
      <p>
        For questions or concerns, contact us at 
        <a href="mailto:connect@agience.ai" className="text-indigo-600 underline ml-1">connect@agience.ai</a> 
        or by mail:
      </p>
      <address className="mt-2 not-italic">
        Ikailo Inc.<br />
        50 Richmond St. E Ste 119 Firm #2048<br />
        Oshawa, ON L1G 7C7<br />
        <a href="mailto:connect@agience.ai" className="text-indigo-600 underline">connect@agience.ai</a>
      </address>
    </div>
  );
};

export default Cookies;
