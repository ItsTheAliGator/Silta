from __future__ import annotations

"""Device image helpers for GUI.

Provides placeholder device images and optional fetching from external sources.
For production use, consider caching images locally or bundling them with the app.
"""

import os
from typing import Optional, Dict


# Map known Logitech devices to image URLs (placeholder approach)
# In production, these would be local bundled images or cached from a CDN
DEVICE_IMAGE_URLS: Dict[int, str] = {
    # MX Master 3
    0xB023: "https://resource.logitech.com/w_316,c_limit,q_auto:best,f_auto,dpr_1.0/d_transparent.gif/content/dam/logitech/en/products/mice/mx-master-3/gallery/mx-master-3-gallery-1.png",
    0x4082: "https://resource.logitech.com/w_316,c_limit,q_auto:best,f_auto,dpr_1.0/d_transparent.gif/content/dam/logitech/en/products/mice/mx-master-3/gallery/mx-master-3-gallery-1.png",
    
    # MX Master 3S
    0xB024: "https://resource.logitech.com/w_316,c_limit,q_auto:best,f_auto,dpr_1.0/d_transparent.gif/content/dam/logitech/en/products/mice/mx-master-3s/gallery/mx-master-3s-gallery-graphite-1.png",
    
    # MX Keys Mini
    0xB369: "https://resource.logitech.com/w_316,c_limit,q_auto:best,f_auto,dpr_1.0/d_transparent.gif/content/dam/logitech/en/products/keyboards/mx-keys-mini/gallery/mx-keys-mini-gallery-graphite-1.png",
    
    # MX Anywhere 3
    0xB019: "https://resource.logitech.com/w_316,c_limit,q_auto:best,f_auto,dpr_1.0/d_transparent.gif/content/dam/logitech/en/products/mice/mx-anywhere-3/gallery/mx-anywhere-3-gallery-graphite-1.png",
}


def get_device_image_url(vendor_id: int, product_id: int) -> Optional[str]:
    """Return the image URL for a known device, or None."""
    if vendor_id == 0x046D:  # Logitech
        return DEVICE_IMAGE_URLS.get(product_id)
    return None


def create_placeholder_image_nsimage(AppKit, device_type: str, size: tuple = (64, 64)):
    """
    Create a placeholder NSImage for a device type.
    
    Uses SF Symbols if available, otherwise creates a simple colored rect.
    """
    try:
        # Try SF Symbols (macOS 11+)
        symbol_names = {
            "mouse": "computermouse.fill",
            "keyboard": "keyboard.fill",
        }
        symbol = symbol_names.get(device_type)
        if symbol and hasattr(AppKit, 'NSImage') and hasattr(AppKit.NSImage, 'imageWithSystemSymbolName_accessibilityDescription_'):
            img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, None)
            if img:
                # Configure the symbol to be larger
                config = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_(size[0] * 0.6, AppKit.NSFontWeightRegular)
                if config:
                    configured_img = img.imageWithSymbolConfiguration_(config)
                    if configured_img:
                        return configured_img
                return img
    except Exception:
        pass
    
    # Fallback: create a simple colored placeholder
    try:
        img = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(*size))
        img.lockFocus()
        
        # Draw device type emoji as a fallback
        emoji_map = {
            "mouse": "🖱️",
            "keyboard": "⌨️",
        }
        emoji = emoji_map.get(device_type, "🔌")
        
        attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(size[0] * 0.5),
        }
        AppKit.NSString.stringWithString_(emoji).drawAtPoint_withAttributes_(
            AppKit.NSMakePoint(size[0] * 0.15, size[1] * 0.15),
            attrs
        )
        
        img.unlockFocus()
        return img
    except Exception:
        return None


def fetch_device_image_async(url: str, callback):
    """
    Fetch a device image asynchronously from URL.
    
    Args:
        url: Image URL
        callback: Function to call with NSImage when ready (or None on failure)
    """
    import threading
    
    def fetch():
        try:
            import urllib.request
            data, _ = urllib.request.urlretrieve(url)
            # Load on main thread
            def load_on_main():
                try:
                    from AppKit import NSImage
                    img = NSImage.alloc().initWithContentsOfFile_(data)
                    callback(img)
                except Exception:
                    callback(None)
            
            from AppKit import NSApp
            NSApp.performSelectorOnMainThread_withObject_waitUntilDone_(
                "performSelector:",
                load_on_main,
                False
            )
        except Exception:
            callback(None)
    
    threading.Thread(target=fetch, daemon=True).start()
