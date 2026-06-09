import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const COOKIE_PREF_KEY = 'cookieConsentAccepted';

const CookieBanner: React.FC = () => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const consent = localStorage.getItem(COOKIE_PREF_KEY);
    if (!consent) setVisible(true);
    if (consent === 'true') {
      window.dispatchEvent(new Event('cookie:analytics-consent'));
    }
  }, []);

  const acceptCookies = () => {
    localStorage.setItem(COOKIE_PREF_KEY, 'true');
    window.dispatchEvent(new Event('cookie:analytics-consent'));
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 inset-x-0 bg-gray-800 text-white text-sm px-4 py-3 z-50 flex justify-between items-center shadow-md">
      <span>
        We use cookies to improve experience. See our{' '}
        <Link to="/cookies" className="underline text-indigo-300">Cookie Policy</Link>.
      </span>
      <div className="flex gap-2 ml-4 shrink-0">
        <button
          onClick={acceptCookies}
          className="bg-indigo-600 hover:bg-indigo-800 text-white px-3 py-1 rounded"
        >
          OK
        </button>        
      </div>
    </div>
  );
};

export default CookieBanner;
