"""浏览器反检测：CDP init script 注入（方案 5.2 StealthPlugin）。

playwright-stealth 长期未维护（2023 年后停滞），此处为自研兜底方案：
在页面加载前注入脚本，隐藏自动化痕迹。
"""

from __future__ import annotations

from playwright.async_api import BrowserContext

STEALTH_SCRIPT = """
(() => {
  const propsToRemove = ['webdriver', 'cdc_adoQpoasnfa76pfcZLmcfl_Array',
    'cdc_adoQpoasnfa76pfcZLmcfl_Promise', 'cdc_adoQpoasnfa76pfcZLmcfl_Symbol'];
  for (const prop of propsToRemove) {
    try { delete Object.getPrototypeOf(navigator)[prop]; } catch (e) {}
    try { delete navigator[prop]; } catch (e) {}
  }
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

  window.chrome = window.chrome || {};
  window.chrome.runtime = window.chrome.runtime || {};
  window.chrome.runtime.connect = window.chrome.runtime.connect || (() => ({}));
  window.chrome.runtime.sendMessage = window.chrome.runtime.sendMessage || (() => {});

  Object.defineProperty(navigator, 'plugins', {
    get: () => [
      { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
      { name: 'Native Client', filename: 'internal-nacl-plugin' }
    ]
  });
  Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });

  const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (originalQuery) {
    window.navigator.permissions.query = (parameters) => {
      if (parameters && parameters.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission });
      }
      return originalQuery(parameters);
    };
  }

  if (window.Notification) {
    Object.defineProperty(Notification, 'permission', { get: () => 'denied' });
  }

  Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
  Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
  Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

  Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth + 14 });
  Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 90 });

  const toString = Function.prototype.toString;
  const nativeToString = (fn) => toString.call(fn);
  if (!nativeToString(navigator.webdriver).includes('[native code]')) {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  }
})();
"""


class StealthPlugin:
    """向 BrowserContext 注入反检测脚本。"""

    def __init__(self, enabled: bool = True, script: str = STEALTH_SCRIPT, fingerprint: bool = False) -> None:
        self.enabled = enabled
        self.script = script
        self.fingerprint = fingerprint

    async def apply(self, context: BrowserContext) -> None:
        if not self.enabled:
            return
        await context.add_init_script(self.script)
        if self.fingerprint:
            from chameleon.anti_detection.fingerprint import FingerprintRandomizer

            await context.add_init_script(FingerprintRandomizer.script())
