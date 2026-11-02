import { useCallback, useEffect, useMemo, useState } from "react";

const money = (value) => new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
}).format(value);

function createConversationId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function loadCart() {
  try {
    const saved = JSON.parse(localStorage.getItem("shop365_cart") || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = sessionStorage.getItem("shop365_token");
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error("Cannot reach Shop365 right now. Check that the backend is running.");
  }

  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.detail || "Something went wrong. Please try again.");
  }
  return result;
}

function Icon({ name, size = 20 }) {
  const paths = {
    bag: <><path d="M5 8h14l1 13H4L5 8Z" /><path d="M9 8V6a3 3 0 0 1 6 0v2" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    spark: <><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    minus: <path d="M5 12h14" />,
  };
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function ProductCard({ product, onAdd }) {
  const icon = {
    Decor: "✦",
    Sweets: "❋",
    Lighting: "☼",
    Gifts: "◇",
  }[product.category] || "✧";

  return (
    <article className="product-card">
      <div className={`product-art art-${product.category.toLowerCase()}`}>
        {product.image_url ? (
          <img src={product.image_url} alt={product.title} loading="lazy" />
        ) : (
          <span aria-hidden="true">{icon}</span>
        )}
        <span className="product-category">{product.category}</span>
      </div>
      <div className="product-details">
        <div className="product-title-row">
          <h3>{product.title}</h3>
          <strong>{money(product.price)}</strong>
        </div>
        <p>{product.description || "A thoughtful find from a Shop365 maker."}</p>
        <div className="product-foot">
          <span>{product.stock} in stock</span>
          <button className="icon-button add-button" type="button" aria-label={`Add ${product.title} to bag`} onClick={() => onAdd(product)}>
            <Icon name="plus" size={18} />
          </button>
        </div>
      </div>
    </article>
  );
}

function AuthDialog({ open, mode, error, onClose, onMode, onLogin, onGuest }) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <button className="icon-button modal-close" type="button" aria-label="Close dialog" onClick={onClose}>
          <Icon name="close" />
        </button>
        <p className="eyebrow">WELCOME TO SHOP365</p>
        <h2 id="auth-title">{mode === "register" ? "Make yourself at home." : "Good things start here."}</h2>
        <div className="auth-tabs">
          <button type="button" className={mode === "login" ? "selected" : ""} onClick={() => onMode("login")}>Sign in</button>
          <button type="button" className={mode === "register" ? "selected" : ""} onClick={() => onMode("register")}>Create account</button>
        </div>
        <form className="stack-form" onSubmit={onLogin}>
          {mode === "register" && (
            <label>Your name<input name="display_name" autoComplete="name" required maxLength={80} /></label>
          )}
          <label>Email address<input name="email" type="email" autoComplete="email" required maxLength={254} /></label>
          <label>Password<input name="password" type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} required minLength={mode === "register" ? 8 : 1} maxLength={128} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-dark full-width" type="submit">{mode === "register" ? "Create your account" : "Sign in"}</button>
        </form>
        <div className="divider"><span>or</span></div>
        <form className="stack-form guest-form" onSubmit={onGuest}>
          <label>Keep it simple<input name="display_name" placeholder="Your name (optional)" maxLength={80} /></label>
          <button className="button button-quiet full-width" type="submit">Continue as a guest</button>
        </form>
      </section>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState(["All"]);
  const [category, setCategory] = useState("All");
  const [search, setSearch] = useState("");
  const [cart, setCart] = useState(loadCart);
  const [authOpen, setAuthOpen] = useState(false);
  const [confirmOrder, setConfirmOrder] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [authError, setAuthError] = useState("");
  const [toast, setToast] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const [aiStatus, setAiStatus] = useState("Checking assistant...");
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hello! I can help you find something special from the live Shop365 collection." },
  ]);
  const [chatBusy, setChatBusy] = useState(false);
  const [conversationId, setConversationId] = useState(() => {
    const saved = sessionStorage.getItem("shop365_conversation");
    return saved || createConversationId();
  });
  const [activity, setActivity] = useState(null);
  const [activityRows, setActivityRows] = useState([]);
  const [activityError, setActivityError] = useState("");

  const cartCount = useMemo(
    () => cart.reduce((total, item) => total + item.quantity, 0),
    [cart],
  );
  const cartTotal = useMemo(
    () => cart.reduce((total, item) => total + item.price * item.quantity, 0),
    [cart],
  );

  const notify = useCallback((message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  }, []);

  const loadProducts = useCallback(async (selectedCategory, term) => {
    const params = new URLSearchParams();
    if (selectedCategory !== "All") params.set("category", selectedCategory);
    if (term.trim()) params.set("search", term.trim());
    const items = await request(`/api/products?${params}`);
    setProducts(items);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([request("/api/categories"), request("/api/ai/status")])
      .then(([items, status]) => {
        if (!active) return;
        setCategories(["All", ...items]);
        setAiStatus(status.configured
          ? `Ready · ${status.memory_turns}-turn memory · bounded retries`
          : "Add GROQ_API_KEY to .env to enable the assistant.");
      })
      .catch((error) => {
        if (active) setAiStatus(error.message);
      });

    const token = sessionStorage.getItem("shop365_token");
    if (token) {
      request("/api/me")
        .then((currentUser) => { if (active) setUser(currentUser); })
        .catch(() => sessionStorage.removeItem("shop365_token"));
    }

    return () => { active = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      const params = new URLSearchParams();
      if (category !== "All") params.set("category", category);
      if (search.trim()) params.set("search", search.trim());
      request(`/api/products?${params}`, { signal: controller.signal })
        .then(setProducts)
        .catch((error) => {
          if (error.name !== "AbortError") notify(error.message);
        });
    }, search ? 220 : 0);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [category, search, notify]);

  useEffect(() => {
    localStorage.setItem("shop365_cart", JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    sessionStorage.setItem("shop365_conversation", conversationId);
  }, [conversationId]);

  function addToCart(product) {
    const existing = cart.find((item) => item.product_id === product.id);
    if (existing?.quantity >= product.stock) {
      notify("That is all the available stock.");
      return;
    }
    setCart((items) => {
      const found = items.find((item) => item.product_id === product.id);
      return found
        ? items.map((item) => item.product_id === product.id
          ? { ...item, quantity: item.quantity + 1 }
          : item)
        : [...items, {
          product_id: product.id,
          quantity: 1,
          title: product.title,
          price: product.price,
        }];
    });
  }

  function changeQuantity(productId, delta) {
    setCart((items) => items
      .map((item) => item.product_id === productId
        ? { ...item, quantity: item.quantity + delta }
        : item)
      .filter((item) => item.quantity > 0));
  }

  function acceptSession(session) {
    sessionStorage.setItem("shop365_token", session.access_token);
    setUser(session.user);
    setAuthError("");
    setAuthOpen(false);
    notify(`Welcome, ${session.user.display_name}.`);
  }

  async function submitAuth(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    const endpoint = authMode === "register" ? "/api/auth/register" : "/api/auth/login";
    try {
      acceptSession(await request(endpoint, {
        method: "POST",
        body: JSON.stringify(payload),
      }));
      form.reset();
    } catch (error) {
      setAuthError(error.message);
    }
  }

  async function continueAsGuest(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const displayName = new FormData(form).get("display_name") || "Diwali Guest";
    try {
      acceptSession(await request("/api/auth/guest", {
        method: "POST",
        body: JSON.stringify({ display_name: displayName }),
      }));
    } catch (error) {
      setAuthError(error.message);
    }
  }

  function signOut() {
    sessionStorage.removeItem("shop365_token");
    setUser(null);
    setActivity(null);
    notify("You have signed out.");
  }

  async function checkout() {
    if (!cart.length) return;
    if (!user) {
      setAuthOpen(true);
      notify("Sign in or continue as a guest to place your order.");
      return;
    }
    setConfirmOrder(true);
  }

  async function placeOrder() {
    setConfirmOrder(false);
    try {
      const order = await request("/api/orders", {
        method: "POST",
        body: JSON.stringify({
          items: cart.map(({ product_id, quantity }) => ({ product_id, quantity })),
        }),
      });
      setCart([]);
      notify(`Order #${order.id} confirmed. No payment was collected.`);
      await loadProducts(category, search);
    } catch (error) {
      notify(error.message);
    }
  }

  async function openActivity(kind) {
    setActivity(kind);
    setActivityRows([]);
    setActivityError("");
    if (!user) return;
    try {
      setActivityRows(await request(kind === "sales" ? "/api/sales" : "/api/orders"));
    } catch (error) {
      setActivityError(error.message);
    }
  }

  async function submitProduct(event) {
    event.preventDefault();
    if (!user || user.is_guest) {
      setAuthMode("register");
      setAuthOpen(true);
      notify("Create an account to list a product.");
      return;
    }
    const form = event.currentTarget;
    const fields = Object.fromEntries(new FormData(form).entries());
    fields.price = Number(fields.price);
    fields.stock = Number(fields.stock);
    try {
      await request("/api/products", {
        method: "POST",
        body: JSON.stringify(fields),
      });
      form.reset();
      await loadProducts(category, search);
      notify("Your product is now listed.");
    } catch (error) {
      notify(error.message);
    }
  }

  async function submitChat(event) {
    event.preventDefault();
    if (chatBusy) return;
    const form = event.currentTarget;
    const message = new FormData(form).get("message").trim();
    if (!message) return;
    form.reset();
    setChatBusy(true);
    setMessages((items) => [
      ...items,
      { role: "user", text: message },
      { role: "assistant", text: "Checking the marketplace..." },
    ]);
    try {
      const result = await request("/api/assistant", {
        method: "POST",
        body: JSON.stringify({ message, conversation_id: conversationId }),
      });
      setMessages((items) => items.map((item, index) =>
        index === items.length - 1 ? { ...item, text: result.answer } : item));
    } catch (error) {
      setMessages((items) => items.map((item, index) =>
        index === items.length - 1 ? { ...item, text: error.message } : item));
    } finally {
      setChatBusy(false);
    }
  }

  function newConversation() {
    setConversationId(createConversationId());
    setMessages([
      { role: "assistant", text: "New conversation started. What would you like to find?" },
    ]);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Shop365 home">
          <span className="brand-symbol">S<span>365</span></span>
          <span>shop<span className="brand-light">365</span></span>
        </a>
        <nav className="main-nav" aria-label="Main navigation">
          <a href="#shop">Discover</a>
          <a href="#assistant" onClick={() => setChatOpen(true)}>The guide</a>
          <a href="#sell">For makers</a>
        </nav>
        <div className="top-actions">
          <button className="bag-link" type="button" onClick={() => document.getElementById("bag")?.scrollIntoView({ behavior: "smooth" })}>
            <Icon name="bag" size={19} /><span>Bag</span><b>{cartCount}</b>
          </button>
          {user ? (
            <div className="signed-in">
              <span className="user-name">{user.display_name}</span>
              <button className="button button-small button-outline" type="button" onClick={signOut}>Sign out</button>
            </div>
          ) : (
            <button className="button button-small button-dark" type="button" onClick={() => setAuthOpen(true)}>Sign in</button>
          )}
        </div>
      </header>

      <main id="home">
        <section className="hero">
          <div className="hero-grain" aria-hidden="true" />
          <div className="hero-copy">
            <p className="eyebrow eyebrow-light"><span /> THE FESTIVE EDIT · 2026</p>
            <h1>Small joys.<br /><em>Big light.</em></h1>
            <p className="hero-description">A more thoughtful way to find the things that make a celebration yours.</p>
            <a className="button button-saffron" href="#shop">Explore the collection <Icon name="arrow" size={17} /></a>
            <div className="hero-note"><span className="note-line" /> Made by people, chosen by you.</div>
          </div>
          <div className="hero-visual" aria-hidden="true">
            <div className="orbit orbit-one" /><div className="orbit orbit-two" />
            <div className="hero-moon" />
            <div className="hero-lamp"><i /></div>
            <span className="hero-star star-a">✳</span><span className="hero-star star-b">✦</span>
            <div className="visual-label">LIGHT · GATHER · GIVE</div>
          </div>
          <div className="hero-index">01 — 03</div>
        </section>

        <section id="shop" className="discover-section section-wrap">
          <div className="section-head">
            <div>
              <p className="eyebrow">A GOOD PLACE TO BEGIN</p>
              <h2>Find your kind of <em>festive.</em></h2>
            </div>
            <label className="search-field">
              <Icon name="search" size={19} />
              <input aria-label="Search products" type="search" placeholder="Try “something sweet”" value={search} onChange={(event) => setSearch(event.target.value)} />
              <kbd>/</kbd>
            </label>
          </div>
          <div className="discovery-tools">
            <div className="category-list" aria-label="Filter by category">
              {categories.map((item) => (
                <button className={`category-pill${category === item ? " active" : ""}`} type="button" key={item} onClick={() => setCategory(item)}>{item}</button>
              ))}
            </div>
            <span className="result-count">{products.length} FINDS</span>
          </div>
          <div className="product-grid">
            {products.length ? products.map((product) => (
              <ProductCard key={product.id} product={product} onAdd={addToCart} />
            )) : <p className="empty-state">Nothing in this corner just yet. Try another category.</p>}
          </div>
        </section>

        <section className="utility-grid section-wrap">
          <section id="bag" className="utility-panel bag-panel">
            <div className="utility-heading">
              <div><p className="eyebrow">THE KEEPERS</p><h2>Your bag <span>{cartCount}</span></h2></div>
              <Icon name="bag" size={22} />
            </div>
            <div className="bag-items">
              {cart.length ? cart.map((item) => (
                <div className="bag-row" key={item.product_id}>
                  <div><strong>{item.title}</strong><span>{money(item.price)} each</span></div>
                  <div className="quantity-stepper">
                    <button type="button" aria-label="Remove one" onClick={() => changeQuantity(item.product_id, -1)}><Icon name="minus" size={14} /></button>
                    <span>{item.quantity}</span>
                    <button type="button" aria-label="Add one" onClick={() => changeQuantity(item.product_id, 1)}><Icon name="plus" size={14} /></button>
                  </div>
                </div>
              )) : <p className="empty-bag">Your bag is ready when you are.</p>}
            </div>
            <div className="bag-total"><span>Subtotal</span><strong>{money(cartTotal)}</strong></div>
            <button className="button button-dark full-width" type="button" disabled={!cart.length} onClick={checkout}>Continue to checkout <Icon name="arrow" size={17} /></button>
            <p className="subtle-note">A demo checkout. No payment is collected.</p>
          </section>

        </section>

        <section id="sell" className="maker-section">
          <div className="maker-copy">
            <p className="eyebrow eyebrow-light">THE PEOPLE BEHIND THE GOOD STUFF</p>
            <h2>Have something<br /><em>worth sharing?</em></h2>
            <p>Set up your maker account and put your work in front of people who love finding something different.</p>
            {user && !user.is_guest && (
              <div className="maker-links">
                <button className="button button-saffron" type="button" onClick={() => openActivity("sales")}>View your sales</button>
                <button className="button button-outline-light" type="button" onClick={() => openActivity("orders")}>Order history</button>
              </div>
            )}
          </div>
          <form className="maker-form" onSubmit={submitProduct}>
            <div className="form-title"><span>01</span><h3>List a new find</h3></div>
            <div className="maker-fields">
              <label>Product name<input name="title" placeholder="The name on the label" required maxLength={120} /></label>
              <label>Category<input name="category" placeholder="Decor, sweets, gifts..." defaultValue="Decor" required maxLength={50} /></label>
              <label>Price in INR<input name="price" type="number" min="1" step="0.01" placeholder="₹ 0.00" required /></label>
              <label>Available stock<input name="stock" type="number" min="0" step="1" placeholder="0" required /></label>
            </div>
            <label className="description-field">A short description<textarea name="description" rows="2" maxLength={1000} placeholder="What makes it special?" /></label>
            <button className="button button-saffron full-width" type="submit">Share it with the bazaar <Icon name="arrow" size={17} /></button>
          </form>
        </section>

        {activity && (
          <section className="activity-section section-wrap">
            <div className="section-head">
              <div><p className="eyebrow">YOUR SHOP365</p><h2>{activity === "sales" ? "Your sales" : "Order history"}</h2></div>
              <button className="button button-outline" type="button" onClick={() => setActivity(null)}>Close</button>
            </div>
            {activityError ? <p className="empty-state">{activityError}</p> : activityRows.length ? (
              <div className="activity-list">
                {activityRows.map((row, index) => (
                  <article className="activity-row" key={row.id || row.order_id || index}>
                    <div><strong>{row.title || `Order #${row.id}`}</strong><p>{row.items || `Buyer: ${row.buyer_name} · ${row.quantity} items · ${row.status}`}</p><small>{row.created_at}</small></div>
                    <strong>{money(row.subtotal ?? row.total)}</strong>
                  </article>
                ))}
              </div>
            ) : <p className="empty-state">Nothing here yet. Your next good thing is just around the corner.</p>}
          </section>
        )}
      </main>

      <div id="assistant" className="assistant-widget">
        {chatOpen && (
          <section id="assistant-panel" className="utility-panel guide-panel assistant-panel" aria-labelledby="assistant-title">
            <div className="utility-heading">
              <div><p className="eyebrow">YOUR LITTLE HELPER</p><h2 id="assistant-title">The Shop365 guide</h2></div>
              <span className="guide-icon"><Icon name="spark" size={21} /></span>
            </div>
            <p className="guide-intro">
              {user && !user.is_guest
                ? `Signed in as ${user.display_name}. Ask about products, orders, or sales.`
                : "Ask about gifts and what’s in stock. Sign in to ask about your orders."}
            </p>
            <div className="chat-log" aria-live="polite">
              {messages.map((message, index) => (
                <p className={`chat-message ${message.role}`} key={`${index}-${message.role}`}>{message.text}</p>
              ))}
            </div>
            <form className="chat-form" onSubmit={submitChat}>
              <input name="message" maxLength={1000} placeholder="What are we looking for?" aria-label="Message the shopping guide" required />
              <button className="button button-dark" type="submit" disabled={chatBusy} aria-label="Send message"><Icon name="arrow" size={17} /></button>
            </form>
            <div className="guide-status"><span className={aiStatus.startsWith("Ready") ? "status-dot ready" : "status-dot"} />{aiStatus}</div>
            <button className="text-button" type="button" onClick={newConversation}>Start a fresh conversation</button>
          </section>
        )}
        <button
          className="assistant-launcher"
          type="button"
          aria-expanded={chatOpen}
          aria-controls="assistant-panel"
          onClick={() => setChatOpen((open) => !open)}
        >
          <Icon name={chatOpen ? "close" : "spark"} size={20} />
          <span>{chatOpen ? "Close chat" : "Chat with Shop365"}</span>
        </button>
      </div>

      <footer className="footer">
        <a className="brand" href="#home"><span className="brand-symbol">S<span>365</span></span><span>shop<span className="brand-light">365</span></span></a>
        <span>A brighter kind of bazaar.</span>
        <span>Made for finding something real.</span>
      </footer>

      <AuthDialog
        open={authOpen}
        mode={authMode}
        error={authError}
        onClose={() => { setAuthOpen(false); setAuthError(""); }}
        onMode={(mode) => { setAuthMode(mode); setAuthError(""); }}
        onLogin={submitAuth}
        onGuest={continueAsGuest}
      />
      {confirmOrder && (
        <div className="modal-backdrop" role="presentation">
          <section className="auth-modal order-confirmation" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
            <p className="eyebrow">ONE LAST LOOK</p>
            <h2 id="confirm-title">Ready to make it yours?</h2>
            <p className="confirm-copy">Your demo order totals <strong>{money(cartTotal)}</strong>. This confirms the order and updates stock; no payment is collected.</p>
            <div className="confirm-actions">
              <button className="button button-quiet" type="button" onClick={() => setConfirmOrder(false)}>Keep browsing</button>
              <button className="button button-dark" type="button" onClick={placeOrder}>Confirm demo order</button>
            </div>
          </section>
        </div>
      )}
      <div className={`toast${toast ? " visible" : ""}`} role="status" aria-live="polite">{toast}</div>
    </div>
  );
}
