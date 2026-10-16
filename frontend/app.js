const API_BASE = (window.MARKETPLACE_API_URL || "").replace(/\/$/, "");
const tokenKey = "near-dear-token";
const userKey = "near-dear-user";
let authMode = "login";
let productsById = new Map();
let toastTimer;

const $ = (selector) => document.querySelector(selector);
const shopView = $("#shop-view");
const reservationsView = $("#reservations-view");
const merchantView = $("#merchant-view");
const authDialog = $("#auth-dialog");
const reservationDialog = $("#reservation-dialog");
const productDialog = $("#product-dialog");

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function currentUser() {
  try { return JSON.parse(localStorage.getItem(userKey) || "null"); }
  catch { return null; }
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  const token = localStorage.getItem(tokenKey);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}/api${path}`, { ...options, headers });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token) signOut(false);
    const detail = data.detail;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join(", ") : detail || "Something went wrong. Please try again.");
  }
  return data;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 3800);
}

function showNotice(message, isError = false) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("error", isError);
  notice.classList.remove("hidden");
  if (!isError) setTimeout(() => notice.classList.add("hidden"), 5000);
}

function setBusy(button, busy, label) {
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = label || "Please wait…";
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

function updateNavigation() {
  const user = currentUser();
  $("#auth-button").textContent = user ? "Sign out" : "Sign in";
  $("#reservations-nav").classList.toggle("hidden", !user || user.role !== "buyer");
  $("#merchant-nav").classList.toggle("hidden", !user || user.role !== "merchant");
}

function showView(view) {
  shopView.classList.toggle("hidden", view !== "shop");
  reservationsView.classList.toggle("hidden", view !== "reservations");
  merchantView.classList.toggle("hidden", view !== "merchant");
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("active"));
  if (view === "shop") $("#shop-nav").classList.add("active");
  if (view === "reservations") $("#reservations-nav").classList.add("active");
  if (view === "merchant") $("#merchant-nav").classList.add("active");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function signOut(showMessage = true) {
  localStorage.removeItem(tokenKey);
  localStorage.removeItem(userKey);
  updateNavigation();
  showView("shop");
  if (showMessage) showToast("You’re signed out. See you around!");
}

function categoryEmoji(category) {
  const value = category.toLowerCase();
  if (value.includes("dairy") || value.includes("milk")) return "🥛";
  if (value.includes("bakery") || value.includes("bread")) return "🥖";
  if (value.includes("vegetable") || value.includes("produce")) return "🍅";
  if (value.includes("station")) return "📓";
  if (value.includes("fruit")) return "🍊";
  if (value.includes("home")) return "🪴";
  return "🛍️";
}

function categoryColor(category) {
  const colors = ["#ececdf", "#f3e9dc", "#e5ede1", "#ece5e8", "#eee9dc"];
  let hash = 0;
  for (const character of category) hash = (hash * 31 + character.charCodeAt(0)) | 0;
  return colors[Math.abs(hash) % colors.length];
}

async function loadCategories() {
  const data = await api("/categories");
  const select = $("#category-filter");
  const selected = select.value;
  select.innerHTML = '<option value="all">All finds</option>' + data.categories.map((category) => (
    `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`
  )).join("");
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;
}

async function loadProducts() {
  const grid = $("#product-grid");
  grid.innerHTML = '<div class="loading-state">Finding your nearby favorites…</div>';
  const query = new URLSearchParams({
    q: $("#search-input").value.trim(),
    category: $("#category-filter").value,
    max_distance: $("#distance-filter").value,
    discounted: String($("#discount-filter").checked),
  });
  try {
    const data = await api(`/products?${query}`);
    productsById = new Map(data.products.map((product) => [product.id, product]));
    if (!data.products.length) {
      grid.innerHTML = '<div class="empty-state"><strong>Nothing on this little list just yet.</strong>Try widening your distance or changing your search.</div>';
      return;
    }
    grid.innerHTML = data.products.map((product) => {
      const emoji = categoryEmoji(product.category);
      return `<article class="product-card">
        <div class="product-visual" style="--product-bg:${categoryColor(product.category)}">
          <span class="product-emoji" aria-hidden="true">${emoji}</span>
          <span class="product-label">${escapeHtml(product.category)}</span>
          ${product.discount_percent > 0 ? `<span class="discount-badge">−${product.discount_percent}%</span>` : ""}
        </div>
        <div class="product-content">
          <h3>${escapeHtml(product.product)}</h3>
          <div class="product-store">${escapeHtml(product.store)}</div>
          <div class="product-price-row"><span class="product-price">₹${Number(product.discount_price).toFixed(0)}</span><span class="old-price">₹${Number(product.price).toFixed(0)}</span></div>
          <div class="product-meta"><span>⌖ ${Number(product.distance_km).toFixed(1)} km away</span><span>${product.quantity} left</span></div>
          <button class="reserve-button" type="button" data-reserve="${product.id}">Reserve this find →</button>
        </div>
      </article>`;
    }).join("");
  } catch (error) {
    grid.innerHTML = `<div class="empty-state"><strong>We couldn't reach the market.</strong>${escapeHtml(error.message)} Check the server and refresh.</div>`;
  }
}

function openAuth() {
  $("#auth-error").classList.add("hidden");
  $("#auth-form").reset();
  setAuthMode("login");
  authDialog.showModal();
}

function setAuthMode(mode) {
  authMode = mode;
  const registering = mode === "register";
  $("#login-mode").classList.toggle("selected", !registering);
  $("#register-mode").classList.toggle("selected", registering);
  $("#auth-title").innerHTML = registering ? "Join your <em>neighborhood.</em>" : "Welcome <em>back.</em>";
  $("#auth-submit").textContent = registering ? "Create account" : "Sign in";
  $("#role-field").classList.toggle("hidden", !registering);
  $("#store-field").classList.toggle("hidden", !registering || $("#auth-form").elements.role.value !== "merchant");
}

function openReservation(productId) {
  const product = productsById.get(Number(productId));
  if (!product) return;
  const user = currentUser();
  if (!user) {
    openAuth();
    showToast("Sign in as a shopper to reserve a local find.");
    return;
  }
  if (user.role !== "buyer") {
    showToast("Shopper accounts can make reservations. Sign in as a shopper to continue.");
    return;
  }
  $("#reservation-error").classList.add("hidden");
  const form = $("#reservation-form");
  form.reset();
  form.elements.product_id.value = String(product.id);
  form.elements.quantity.max = String(product.quantity);
  $("#reservation-product").innerHTML = `<span class="reservation-thumb">${categoryEmoji(product.category)}</span><span><strong>${escapeHtml(product.product)}</strong><small>${escapeHtml(product.store)} · ₹${Number(product.discount_price).toFixed(0)} each · ${product.quantity} available</small></span>`;
  $("#delivery-field").classList.add("hidden");
  reservationDialog.showModal();
}

async function loadBuyerReservations() {
  const container = $("#buyer-reservations");
  container.innerHTML = '<div class="loading-state">Gathering your local finds…</div>';
  try {
    const data = await api("/reservations");
    if (!data.reservations.length) {
      container.innerHTML = '<div class="empty-state"><strong>No reservations yet.</strong>Your next favorite might be just around the corner.</div>';
      return;
    }
    container.innerHTML = data.reservations.map((reservation) => `
      <article class="reservation-card">
        <div class="reservation-info"><span class="reservation-thumb">${categoryEmoji(reservation.product.category)}</span><div><h3>${escapeHtml(reservation.product.product)} · ${reservation.quantity}</h3><p>${escapeHtml(reservation.product.store)} · ${reservation.fulfillment === "pickup" ? "Store pickup" : `Delivery to ${escapeHtml(reservation.delivery_address)}`}<br />Requested ${new Date(reservation.created_at).toLocaleString()}</p></div></div>
        <span class="reservation-status status-${escapeHtml(reservation.status)}">${escapeHtml(reservation.status)}</span>
        ${!["cancelled", "completed"].includes(reservation.status) ? `<button class="cancel-reservation" data-cancel-reservation="${reservation.id}" type="button">Cancel</button>` : ""}
      </article>`).join("");
  } catch (error) {
    container.innerHTML = `<div class="empty-state"><strong>Could not load reservations.</strong>${escapeHtml(error.message)}</div>`;
  }
}

async function loadMerchantStudio() {
  const productsArea = $("#merchant-products");
  const reservationsArea = $("#merchant-reservations");
  productsArea.innerHTML = '<div class="loading-state">Opening your studio…</div>';
  try {
    const [productData, reservationData] = await Promise.all([
      api("/merchant/products"),
      api("/merchant/reservations"),
    ]);
    if (!productData.products.length) {
      productsArea.innerHTML = '<div class="empty-state"><strong>Your shop starts with one good find.</strong>Add a listing to show local shoppers what you have.</div>';
    } else {
      productsArea.innerHTML = productData.products.map((product) => `
        <article class="merchant-product">
          <div><h3>${escapeHtml(product.product)}</h3><p>${escapeHtml(product.category)} · ₹${Number(product.discount_price).toFixed(0)} · ${product.quantity} available · ${product.active ? "Active" : "Inactive"}</p></div>
          <div class="merchant-actions"><button class="text-button" data-edit-product="${product.id}" type="button">Edit</button>${product.active ? `<button class="text-button danger" data-deactivate-product="${product.id}" type="button">Deactivate</button>` : ""}</div>
        </article>`).join("");
    }
    if (!reservationData.reservations.length) {
      reservationsArea.innerHTML = '<div class="empty-state"><strong>No reservations to tend to just yet.</strong>They will show up here when a neighbor saves a find.</div>';
    } else {
      reservationsArea.innerHTML = reservationData.reservations.map((reservation) => {
        const actions = reservation.status === "pending" ? ["confirmed", "cancelled"]
          : reservation.status === "confirmed" ? ["ready", "cancelled"]
            : reservation.status === "ready" ? ["completed", "cancelled"] : [];
        const controls = actions.length ? `<div class="reservation-controls"><select aria-label="New status for reservation ${reservation.id}" data-reservation-status="${reservation.id}">${actions.map((status) => `<option value="${status}">${status}</option>`).join("")}</select><button data-update-reservation="${reservation.id}" type="button">Update</button></div>` : "";
        return `<article class="reservation-card"><div class="reservation-info"><span class="reservation-thumb">${categoryEmoji(reservation.product.category)}</span><div><h3>${escapeHtml(reservation.product.product)} · ${reservation.quantity}</h3><p>${escapeHtml(reservation.product.store)} · ${reservation.fulfillment === "pickup" ? "Store pickup" : `Delivery to ${escapeHtml(reservation.delivery_address)}`}<br />${new Date(reservation.created_at).toLocaleString()}</p></div></div><span class="reservation-status status-${escapeHtml(reservation.status)}">${escapeHtml(reservation.status)}</span>${controls}</article>`;
      }).join("");
    }
  } catch (error) {
    productsArea.innerHTML = `<div class="empty-state"><strong>Could not load your studio.</strong>${escapeHtml(error.message)}</div>`;
    reservationsArea.innerHTML = "";
  }
}

function openProductForm(product = null) {
  const form = $("#product-form");
  form.reset();
  $("#product-error").classList.add("hidden");
  $("#product-form-title").innerHTML = product ? "Edit your <em>listing.</em>" : "Add a <em>listing.</em>";
  form.elements.id.value = product ? String(product.id) : "";
  if (product) {
    for (const field of ["product", "category", "description", "store", "price", "discount_price", "quantity", "distance_km"]) {
      form.elements[field].value = product[field];
    }
  } else {
    form.elements.store.value = currentUser()?.store_name || "";
    form.elements.distance_km.value = "1";
    form.elements.quantity.value = "1";
  }
  productDialog.showModal();
}

$("#auth-button").addEventListener("click", () => currentUser() ? signOut() : openAuth());
$("#shop-nav").addEventListener("click", () => { showView("shop"); loadProducts(); });
$("#reservations-nav").addEventListener("click", () => { showView("reservations"); loadBuyerReservations(); });
$("#merchant-nav").addEventListener("click", () => { showView("merchant"); loadMerchantStudio(); });
$("#login-mode").addEventListener("click", () => setAuthMode("login"));
$("#register-mode").addEventListener("click", () => setAuthMode("register"));
$("#auth-form").elements.role.addEventListener("change", () => setAuthMode(authMode));
$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("#auth-submit");
  const error = $("#auth-error");
  error.classList.add("hidden");
  setBusy(button, true, "One moment…");
  const payload = Object.fromEntries(new FormData(form));
  if (authMode === "login" || payload.role !== "merchant") delete payload.store_name;
  try {
    const result = await api(`/auth/${authMode === "login" ? "login" : "register"}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    localStorage.setItem(tokenKey, result.token);
    localStorage.setItem(userKey, JSON.stringify(result.user));
    updateNavigation();
    authDialog.close();
    showToast(`Welcome${result.user.store_name ? `, ${result.user.store_name}` : ""}!`);
    if (result.user.role === "merchant") {
      showView("merchant");
      loadMerchantStudio();
    }
  } catch (requestError) {
    error.textContent = requestError.message;
    error.classList.remove("hidden");
  } finally {
    setBusy(button, false);
  }
});

$("#product-grid").addEventListener("click", (event) => {
  const button = event.target.closest("[data-reserve]");
  if (button) openReservation(button.dataset.reserve);
});
for (const eventName of ["input", "change"]) {
  $("#search-input").addEventListener(eventName, loadProducts);
  $("#category-filter").addEventListener(eventName, loadProducts);
  $("#distance-filter").addEventListener(eventName, loadProducts);
  $("#discount-filter").addEventListener(eventName, loadProducts);
}

$("#reservation-form").elements.fulfillment.addEventListener("change", (event) => {
  const delivery = event.target.value === "delivery";
  $("#delivery-field").classList.toggle("hidden", !delivery);
  $("#reservation-form").elements.delivery_address.required = delivery;
});
$("#reservation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const error = $("#reservation-error");
  error.classList.add("hidden");
  setBusy(button, true, "Saving your request…");
  const data = Object.fromEntries(new FormData(form));
  data.product_id = Number(data.product_id);
  data.quantity = Number(data.quantity);
  try {
    await api("/reservations", { method: "POST", body: JSON.stringify(data) });
    reservationDialog.close();
    showToast("Reservation requested! The shop will confirm with you.");
    await loadProducts();
    if (!reservationsView.classList.contains("hidden")) loadBuyerReservations();
  } catch (requestError) {
    error.textContent = requestError.message;
    error.classList.remove("hidden");
  } finally {
    setBusy(button, false);
  }
});

$("#buyer-reservations").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-cancel-reservation]");
  if (!button || !confirm("Cancel this reservation? The stock will be returned to the listing.")) return;
  button.disabled = true;
  try {
    await api(`/reservations/${button.dataset.cancelReservation}/cancel`, { method: "POST" });
    showToast("Reservation cancelled.");
    await loadBuyerReservations();
    await loadProducts();
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
  }
});

$("#add-product-button").addEventListener("click", () => openProductForm());
$("#merchant-products").addEventListener("click", async (event) => {
  const edit = event.target.closest("[data-edit-product]");
  if (edit) {
    try {
      const data = await api("/merchant/products");
      const product = data.products.find((item) => item.id === Number(edit.dataset.editProduct));
      if (product) openProductForm(product);
    } catch (error) { showToast(error.message); }
    return;
  }
  const deactivate = event.target.closest("[data-deactivate-product]");
  if (deactivate && confirm("Deactivate this listing? It will no longer appear to shoppers.")) {
    try {
      await api(`/products/${deactivate.dataset.deactivateProduct}`, { method: "DELETE" });
      showToast("Listing deactivated.");
      loadMerchantStudio();
    } catch (error) { showToast(error.message); }
  }
});

$("#product-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const error = $("#product-error");
  error.classList.add("hidden");
  const data = Object.fromEntries(new FormData(form));
  const id = data.id;
  delete data.id;
  for (const field of ["price", "discount_price", "distance_km"]) data[field] = Number(data[field]);
  data.quantity = Number(data.quantity);
  setBusy(button, true, "Saving listing…");
  try {
    await api(id ? `/products/${id}` : "/products", { method: id ? "PATCH" : "POST", body: JSON.stringify(data) });
    productDialog.close();
    showToast(id ? "Listing updated." : "Your listing is live.");
    await loadMerchantStudio();
    await loadCategories();
    await loadProducts();
  } catch (requestError) {
    error.textContent = requestError.message;
    error.classList.remove("hidden");
  } finally {
    setBusy(button, false);
  }
});

$("#merchant-reservations").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-update-reservation]");
  if (!button) return;
  const id = button.dataset.updateReservation;
  const value = $(`[data-reservation-status="${id}"]`).value;
  button.disabled = true;
  try {
    await api(`/merchant/reservations/${id}`, { method: "PATCH", body: JSON.stringify({ status: value }) });
    showToast(`Reservation marked ${value}.`);
    await loadMerchantStudio();
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
  }
});

document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => document.getElementById(button.dataset.close).close());
});

async function start() {
  updateNavigation();
  try {
    await loadCategories();
    await loadProducts();
  } catch {
    showNotice("The marketplace API is not available yet. Start the server and refresh.", true);
  }
}

start();
