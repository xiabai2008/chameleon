"""浏览器指纹深度随机化：Canvas/WebGL/Audio 噪声注入（方案 P8-6）。"""

from __future__ import annotations

import secrets

FINGERPRINT_SCRIPT_TEMPLATE = """
(() => {
  const noise = () => {{
    return __NOISE__ + (Math.random() * __AMPLITUDE__ - __AMPLITUDE__ / 2);
  }};

  // Canvas 指纹噪声
  const originalGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function(type, ...args) {{
    const ctx = originalGetContext.call(this, type, ...args);
    if (ctx && (type === '2d' || type === 'webgl' || type === 'webgl2')) {{
      const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toDataURL = function(...dargs) {{
        const imageData = ctx.getImageData ? ctx.getImageData(0, 0, this.width, this.height) : null;
        if (imageData) {{
          const data = imageData.data;
          for (let i = 0; i < data.length; i += 257) {{
            data[i] = Math.max(0, Math.min(255, data[i] + noise()));
          }}
          ctx.putImageData(imageData, 0, 0);
        }}
        return originalToDataURL.apply(this, dargs);
      }};
    }}
    return ctx;
  }};

  // WebGL 参数噪声
  try {{
    const gl = document.createElement('canvas').getContext('webgl');
    if (gl) {{
      const origParam = gl.getParameter.bind(gl);
      gl.getParameter = function(p) {{
        const value = origParam(p);
        if (typeof value === 'number' && value > 1 && p !== 37445 && p !== 37446) {{
          return value + noise();
        }}
        return value;
      }};
    }}
  }} catch (e) {{}}

  // Audio 指纹噪声
  try {{
    const origGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = function(channel) {{
      const data = origGetChannelData.call(this, channel);
      for (let i = 0; i < data.length; i += 131) {{
        data[i] += noise() * 0.001;
      }}
      return data;
    }};
  }} catch (e) {{}}
}})();
"""


class FingerprintRandomizer:
    """生成带随机噪声参数的指纹注入脚本。"""

    @classmethod
    def script(cls) -> str:
        noise = round(secrets.randbelow(4) + 0.5, 2)
        amplitude = round(secrets.randbelow(30) / 10 + 0.05, 2)
        return (
            FINGERPRINT_SCRIPT_TEMPLATE
            .replace("__NOISE__", str(noise))
            .replace("__AMPLITUDE__", str(amplitude))
        )

    @classmethod
    def script_many(cls, count: int) -> list[str]:
        return [cls.script() for _ in range(count)]
