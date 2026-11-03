// ===============================
// TRAVELVERSE AUTH & BACKEND SYNC
// ===============================

const API_BASE = "http://127.0.0.1:8000";

// Toast Helper
function showToast(type, title, message) {
    const toast = document.getElementById("travel-toast");
    const toastIcon = document.getElementById("toast-icon");
    const toastTitle = document.getElementById("toast-title");
    const toastMessage = document.getElementById("toast-message");

    if (!toast) return;

    toast.classList.remove("success", "error");
    toast.classList.add(type);

    if (toastIcon) toastIcon.textContent = type === "success" ? "✓" : "!";
    if (toastTitle) toastTitle.textContent = title;
    if (toastMessage) toastMessage.textContent = message;

    toast.classList.add("show");

    clearTimeout(window.travelToastTimer);
    window.travelToastTimer = setTimeout(() => {
        toast.classList.remove("show");
    }, 4000);
}

window.showToast = showToast;

document.addEventListener("click", (e) => {
    if (e.target && e.target.id === "toast-close") {
        const toast = document.getElementById("travel-toast");
        if (toast) toast.classList.remove("show");
    }
});

// Immediately deduplicate any existing travelverse_accounts in localStorage on page load
(function pruneDuplicateLocalAccounts() {
    try {
        const raw = JSON.parse(localStorage.getItem("travelverse_accounts") || "[]");
        if (!Array.isArray(raw)) return;
        const uniqueMap = new Map();
        raw.forEach(acc => {
            if (acc && acc.email) {
                const key = String(acc.email).trim().toLowerCase();
                if (!uniqueMap.has(key)) {
                    uniqueMap.set(key, acc);
                }
            }
        });
        localStorage.setItem("travelverse_accounts", JSON.stringify(Array.from(uniqueMap.values())));
    } catch (e) {}
})();

function getAccounts() {
    try {
        return JSON.parse(localStorage.getItem("travelverse_accounts") || "[]");
    } catch (e) {
        return [];
    }
}

function saveAccounts(accounts) {
    try {
        const uniqueMap = new Map();
        (accounts || []).forEach(acc => {
            if (acc && acc.email) {
                const key = String(acc.email).trim().toLowerCase();
                uniqueMap.set(key, acc);
            }
        });
        localStorage.setItem("travelverse_accounts", JSON.stringify(Array.from(uniqueMap.values())));
    } catch (e) {}
}

function setActiveSession(user) {
    try {
        const email = user.email || "";
        const firstName = user.firstName || user.first_name || "";
        const lastName = user.lastName || user.last_name || "";
        const fullName = (firstName + (lastName ? " " + lastName : "")).trim();
        const username = user.username || "";

        localStorage.setItem("travelverse_current_user_email", email);
        if (fullName) localStorage.setItem("travelverse_user_name", fullName);
        else if (user.name) localStorage.setItem("travelverse_user_name", user.name);

        if (username) localStorage.setItem("travelverse_username", username);

        localStorage.setItem("travelverse_badges", JSON.stringify(user.badges || []));
        localStorage.setItem("travelverse_profile_pic", user.profilePic || user.profile_pic || "");
        localStorage.setItem("travelverse_session_active", "true");
    } catch (e) {}
}

// Sync users from DB on page load so created accounts & passwords are remembered
async function syncAccountsFromBackend() {
    try {
        const res = await fetch(`${API_BASE}/all-users`);
        if (res.ok) {
            const data = await res.json();
            if (data.status === "success" && Array.isArray(data.users)) {
                const existingLocal = getAccounts();
                const validMap = new Map();

                // 1. Populate map with users from backend database
                data.users.forEach(u => {
                    if (u && u.email) {
                        const emailKey = String(u.email).trim().toLowerCase();
                        const existing = existingLocal.find(a => a && a.email && String(a.email).trim().toLowerCase() === emailKey) || {};
                        validMap.set(emailKey, {
                            ...existing,
                            firstName: u.first_name || existing.firstName || "Traveler",
                            lastName: u.last_name || existing.lastName || "",
                            username: u.username || existing.username || emailKey.split("@")[0],
                            email: u.email,
                            password: u.password || existing.password || "travel123",
                            badges: (u.badges && u.badges.length) ? u.badges : (existing.badges || []),
                            profilePic: u.profile_pic || existing.profilePic || ""
                        });
                    }
                });

                // 2. Push any local accounts created while backend was offline to MongoDB
                for (const localAcc of existingLocal) {
                    if (localAcc && localAcc.email) {
                        const emailKey = String(localAcc.email).trim().toLowerCase();
                        if (!validMap.has(emailKey)) {
                            try {
                                const regRes = await fetch(`${API_BASE}/register`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({
                                        first_name: localAcc.firstName || "Traveler",
                                        last_name: localAcc.lastName || "",
                                        username: localAcc.username || emailKey.split("@")[0],
                                        email: localAcc.email,
                                        password: localAcc.password || "travel123",
                                        badges: localAcc.badges || []
                                    })
                                });
                                if (regRes.ok) {
                                    const regData = await regRes.json();
                                    validMap.set(emailKey, localAcc);
                                    console.log(`[Sync] Pushed unsynced account (${emailKey}) to MongoDB.`);
                                }
                            } catch (syncErr) {
                                console.warn("[Sync] Failed to push local account to backend:", syncErr);
                            }
                        }
                    }
                }

                saveAccounts(Array.from(validMap.values()));
            }
        }
    } catch (err) {
        console.log("Backend sync note:", err);
    }
}
syncAccountsFromBackend();

// ===============================
// SIGNUP & LOGIN FORM HANDLERS
// ===============================
function initAuth() {
    const signupStep1 = document.getElementById("signup-step1");
    const signupStep2 = document.getElementById("signup-step2");
    const signupStep3 = document.getElementById("signup-step3");
    const signupOtpBox = document.getElementById("signup-otp-box");
    const sendOtpBtn = document.getElementById("signup-send-otp-btn");
    const verifyOtpBtn = document.getElementById("signup-verify-otp-btn");
    const resendBtn = document.getElementById("signup-resend-otp-btn");
    const stepIndicator = document.getElementById("step-indicator");
    const registerCopy = document.getElementById("register-copy");

    let isEmailVerified = false;

    // Helper to update Step Headers
    function updateStepHeader(step) {
        if (!registerCopy) return;
        const h2 = registerCopy.querySelector(".headline");
        const sub = registerCopy.querySelector(".sub");
        if (step === 1) {
            if (stepIndicator) stepIndicator.textContent = "Step 1 of 3";
            if (h2) h2.textContent = "Verify your email";
            if (sub) sub.textContent = "Enter your email to receive a 6-digit verification code.";
        } else if (step === 2) {
            if (stepIndicator) stepIndicator.textContent = "Step 2 of 3";
            if (h2) h2.textContent = "Create your password";
            if (sub) sub.textContent = "Choose a secure password for your account.";
        } else if (step === 3) {
            if (stepIndicator) stepIndicator.textContent = "Step 3 of 3";
            if (h2) h2.textContent = "Complete your profile";
            if (sub) sub.textContent = "Enter your name and username handle.";
        }
    }

    // STEP 1a: Send OTP to Email
    async function handleSendEmailOTP() {
        const emailInput = document.getElementById("reg-email");
        const email = emailInput ? emailInput.value.trim().toLowerCase() : "";

        if (!email || !email.includes("@")) {
            showToast("error", "Invalid Email", "Please enter a valid email address.");
            return;
        }

        if (sendOtpBtn) {
            sendOtpBtn.disabled = true;
            sendOtpBtn.textContent = "Sending Code…";
        }

        try {
            const response = await fetch(`${API_BASE}/send-signup-email-otp`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: email })
            });

            const data = await response.json();

            if (!response.ok) {
                showToast("error", "Email Check Failed", data.detail || "Could not send verification code.");
                return;
            }

            if (signupOtpBox) signupOtpBox.style.display = "block";
            if (sendOtpBtn) signupSendOtpBtnHide();

            const targetEmailEl = document.getElementById("signup-target-email");
            if (targetEmailEl) targetEmailEl.textContent = email;

            showToast("success", "Code Sent!", `A 6-digit verification code was sent to ${email}. Check your inbox!`);

        } catch (err) {
            console.warn("Backend connection error sending signup OTP:", err);
            showToast("error", "Connection Error", "Could not connect to backend server. Please ensure backend is running.");
        } finally {
            if (sendOtpBtn) {
                sendOtpBtn.disabled = false;
                sendOtpBtn.textContent = "Send Verification Code →";
            }
        }
    }

    function signupSendOtpBtnHide() {
        if (sendOtpBtn) sendOtpBtn.style.display = "none";
    }

    if (sendOtpBtn) {
        sendOtpBtn.addEventListener("click", (e) => {
            e.preventDefault();
            handleSendEmailOTP();
        });
    }

    if (resendBtn) {
        resendBtn.addEventListener("click", (e) => {
            e.preventDefault();
            handleSendEmailOTP();
        });
    }

    // STEP 1b: Verify OTP Code
    if (verifyOtpBtn) {
        verifyOtpBtn.addEventListener("click", async (e) => {
            e.preventDefault();

            const emailInput = document.getElementById("reg-email");
            const email = emailInput ? emailInput.value.trim().toLowerCase() : "";
            const otpInput = document.getElementById("signup-otp-input");
            const otp = otpInput ? otpInput.value.trim() : "";

            if (!otp || otp.length !== 6) {
                showToast("error", "Invalid Code", "Please enter the complete 6-digit OTP code.");
                return;
            }

            verifyOtpBtn.disabled = true;
            verifyOtpBtn.textContent = "Verifying Code…";

            try {
                const response = await fetch(`${API_BASE}/verify-signup-email-otp`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: email, otp: otp })
                });

                const data = await response.json();

                if (!response.ok) {
                    showToast("error", "Verification Failed", data.detail || "Invalid code. Please try again.");
                    return;
                }

                isEmailVerified = true;
                showToast("success", "Email Verified!", "Your email is confirmed. Please set your password.");

                // Transition to Step 2 (Password)
                if (signupStep1) signupStep1.style.display = "none";
                if (signupStep2) signupStep2.style.display = "block";
                updateStepHeader(2);

            } catch (err) {
                console.warn("Error verifying signup OTP:", err);
                showToast("error", "Connection Error", "Could not verify code. Please check your backend.");
            } finally {
                verifyOtpBtn.disabled = false;
                verifyOtpBtn.textContent = "Verify Email →";
            }
        });
    }

    // STEP 2: Password Next & Back
    const step2NextBtn = document.getElementById("signup-step2-next-btn");
    const step2BackBtn = document.getElementById("signup-step2-back-btn");

    if (step2NextBtn) {
        step2NextBtn.addEventListener("click", () => {
            const passwordInput = document.getElementById("reg-password");
            const password = passwordInput ? passwordInput.value : "";

            if (!password || password.length < 6) {
                showToast("error", "Password Too Short", "Please enter a password with at least 6 characters.");
                return;
            }

            // Transition to Step 3 (Profile Details)
            if (signupStep2) signupStep2.style.display = "none";
            if (signupStep3) signupStep3.style.display = "block";
            updateStepHeader(3);
            const curRole = (window.CURRENT_ROLE || "traveller").toLowerCase();
            if (curRole === "agent") {
                setTimeout(() => {
                    if (typeof window.openAgentRegisterModal === "function") {
                        window.openAgentRegisterModal();
                    }
                }, 80);
            }
        });
    }

    if (step2BackBtn) {
        step2BackBtn.addEventListener("click", () => {
            if (signupStep2) signupStep2.style.display = "none";
            if (signupStep1) signupStep1.style.display = "block";
            updateStepHeader(1);
        });
    }

    // STEP 3: Profile Details Back & Complete Registration
    const step3BackBtn = document.getElementById("signup-step3-back-btn");
    const completeBtn = document.getElementById("signup-complete-btn");
    const registerForm = document.getElementById("register-form");

    if (step3BackBtn) {
        step3BackBtn.addEventListener("click", () => {
            if (signupStep3) signupStep3.style.display = "none";
            if (signupStep2) signupStep2.style.display = "block";
            updateStepHeader(2);
        });
    }

    async function handleCompleteRegistration() {
        const emailInput = document.getElementById("reg-email");
        const email = emailInput ? emailInput.value.trim().toLowerCase() : "";
        const passwordInput = document.getElementById("reg-password");
        const password = passwordInput ? passwordInput.value : "";
        const role = (window.CURRENT_ROLE || "traveller").toLowerCase();

        let reqPayload = {
            email: email,
            password: password,
            role: role
        };

        if (role === "agent") {
            const agentLeadName = document.getElementById("agent-lead-name") ? document.getElementById("agent-lead-name").value.trim() : "";
            const agentAgencyName = document.getElementById("agent-agency-name") ? document.getElementById("agent-agency-name").value.trim() : "";
            const agentUsername = document.getElementById("agent-username") ? document.getElementById("agent-username").value.trim() : "";
            const agentType = document.getElementById("agent-type-select") ? document.getElementById("agent-type-select").value : "person";
            const agentPhone = document.getElementById("agent-phone") ? document.getElementById("agent-phone").value.trim() : "";
            const agentSpecialty = document.getElementById("agent-specialty") ? document.getElementById("agent-specialty").value.trim() : "";
            const agentDestinations = document.getElementById("agent-destinations") ? document.getElementById("agent-destinations").value.trim() : "";
            const agentExperience = document.getElementById("agent-experience") ? parseInt(document.getElementById("agent-experience").value) || 3 : 3;
            const agentLanguages = document.getElementById("agent-languages") ? document.getElementById("agent-languages").value.trim() : "English";
            const agentBio = document.getElementById("agent-bio") ? document.getElementById("agent-bio").value.trim() : "";

            if (!agentLeadName) {
                showToast("error", "Name Required", "Please enter the agent or lead guide name.");
                return;
            }
            if (!agentAgencyName) {
                showToast("error", "Agency Required", "Please enter the agency or company name.");
                return;
            }

            const names = agentLeadName.split(" ");
            reqPayload.first_name = names[0];
            reqPayload.last_name = names.slice(1).join(" ") || "Agent";
            reqPayload.username = agentUsername || agentLeadName.toLowerCase().replace(/\s+/g, "_");
            reqPayload.agent_name = agentLeadName;
            reqPayload.agency_name = agentAgencyName;
            reqPayload.agent_type = agentType;
            reqPayload.phone = agentPhone;
            reqPayload.specialty = agentSpecialty || "Custom Expeditions";
            reqPayload.destinations = agentDestinations || "Global";
            reqPayload.experience_years = agentExperience;
            reqPayload.languages = agentLanguages;
            reqPayload.bio = agentBio;
            reqPayload.badges = ["Verified Partner Agent"];
        } else {
            const firstName = document.getElementById("first-name") ? document.getElementById("first-name").value.trim() : "";
            const lastName = document.getElementById("last-name") ? document.getElementById("last-name").value.trim() : "";
            const username = document.getElementById("username") ? document.getElementById("username").value.trim() : "";

            if (!firstName) {
                showToast("error", "First Name Missing", "Please enter your first name.");
                return;
            }
            if (!lastName) {
                showToast("error", "Last Name Missing", "Please enter your last name.");
                return;
            }
            if (!username) {
                showToast("error", "Username Missing", "Please enter a username handle.");
                return;
            }

            reqPayload.first_name = firstName;
            reqPayload.last_name = lastName;
            reqPayload.username = username;
            reqPayload.badges = [];
        }

        if (completeBtn) {
            completeBtn.disabled = true;
            completeBtn.textContent = "Creating Account…";
        }
        const popupSubmitBtn = document.getElementById("agent-popup-submit-btn");
        if (popupSubmitBtn) {
            popupSubmitBtn.disabled = true;
            popupSubmitBtn.textContent = "Creating Account…";
        }

        try {
            const response = await fetch(`${API_BASE}/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(reqPayload)
            });

            const data = await response.json();

            if (!response.ok) {
                showToast("error", "Registration Failed", data.detail || "Account creation failed.");
                return;
            }

            const u = data.user;
            const assignedRole = data.role || role;
            const newAccount = {
                firstName: u.first_name,
                lastName: u.last_name,
                username: u.username,
                email: u.email,
                role: assignedRole,
                password: password,
                badges: u.badges || [],
                profilePic: u.profile_pic || "",
                agencyName: u.agency_name || ""
            };

            const accounts = getAccounts();
            const existingIdx = accounts.findIndex(acc => acc && acc.email && acc.email.toLowerCase() === email);
            if (existingIdx >= 0) accounts[existingIdx] = newAccount;
            else accounts.push(newAccount);

            saveAccounts(accounts);
            setActiveSession(newAccount);

            localStorage.setItem("travelverse_current_user_role", assignedRole);
            if (data.agent) {
                localStorage.setItem("travelverse_agent_profile", JSON.stringify(data.agent));
            }

            if (typeof window.closeAgentRegisterModal === "function") {
                window.closeAgentRegisterModal();
            }
            const targetPage = (assignedRole === "agent") ? "agent-dashboard.html" : "dashboard.html";
            showToast("success", "Account Created!", `Registration complete as ${assignedRole}. Redirecting to your portal…`);
            setTimeout(() => {
                window.location.href = targetPage;
            }, 900);

        } catch (err) {
            console.warn("Error completing registration:", err);
            showToast("error", "Connection Error", "Could not complete registration. Please try again.");
        } finally {
            if (completeBtn) {
                completeBtn.disabled = false;
                completeBtn.textContent = "Complete Registration →";
            }
            const popupSubmitBtn = document.getElementById("agent-popup-submit-btn");
            if (popupSubmitBtn) {
                popupSubmitBtn.disabled = false;
                popupSubmitBtn.textContent = "✓ Complete Agent Registration →";
            }
        }
    }

    if (completeBtn) {
        completeBtn.addEventListener("click", (e) => {
            e.preventDefault();
            handleCompleteRegistration();
        });
    }

    if (registerForm) {
        registerForm.addEventListener("submit", (e) => {
            e.preventDefault();
            if (signupStep3 && signupStep3.style.display !== "none") {
                handleCompleteRegistration();
            }
        });
    }

    const loginForm = document.getElementById("login-form");
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const emailInput = document.getElementById("login-email") ? document.getElementById("login-email").value.trim() : "";
            const passwordInput = document.getElementById("login-password") ? document.getElementById("login-password").value : "";

            if (!emailInput || passwordInput.length < 6) {
                showToast("error", "Check your details", "Please enter a valid email or username and a password of at least 6 characters.");
                return;
            }

            const submitBtn = loginForm.querySelector(".submit");
            const originalText = submitBtn ? submitBtn.textContent : "";
            if (submitBtn) {
                submitBtn.textContent = "Logging in…";
                submitBtn.disabled = true;
            }

            try {
                const currentRole = (window.CURRENT_ROLE || "traveller").toLowerCase();
                const response = await fetch(`${API_BASE}/login`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        email_or_username: emailInput,
                        password: passwordInput,
                        expected_role: currentRole
                    })
                });

                const data = await response.json();

                if (response.ok && data.status === "success") {
                    const u = data.user;
                    let assignedRole = String(data.role || (u && u.role) || "").toLowerCase();
                    if (data.agent || (u && (u.agent_id || u.agency_name)) || assignedRole === "agent") {
                        assignedRole = "agent";
                    } else {
                        assignedRole = assignedRole || "traveller";
                    }
                    const userObj = {
                        firstName: u.first_name,
                        lastName: u.last_name,
                        username: u.username,
                        email: u.email,
                        role: assignedRole,
                        password: passwordInput,
                        badges: u.badges || [],
                        profilePic: u.profile_pic || "",
                        agencyName: u.agency_name || ""
                    };

                    const accounts = getAccounts();
                    const existingIdx = accounts.findIndex(acc => acc.email.toLowerCase() === u.email.toLowerCase());
                    if (existingIdx >= 0) {
                        accounts[existingIdx] = { ...accounts[existingIdx], ...userObj };
                    } else {
                        accounts.push(userObj);
                    }
                    saveAccounts(accounts);

                    setActiveSession(userObj);
                    localStorage.setItem("travelverse_current_user_role", assignedRole);
                    if (data.agent) {
                        localStorage.setItem("travelverse_agent_profile", JSON.stringify(data.agent));
                    }

                    const targetPage = (assignedRole === "agent") ? "agent-dashboard.html" : "dashboard.html";
                    window.location.href = targetPage;
                    return;
                } else {
                    showToast("error", "Couldn't log you in", data.detail || "The email/username or password you entered is incorrect.");
                    return;
                }
            } catch (error) {
                console.warn("Backend server unreachable during login, checking local fallback:", error);
                const accounts = getAccounts();
                const matchedUser = accounts.find(acc =>
                    (acc.email.toLowerCase() === emailInput.toLowerCase() || acc.username.toLowerCase() === emailInput.toLowerCase()) &&
                    acc.password === passwordInput
                );

                if (matchedUser) {
                    let assignedRole = String(matchedUser.role || "").toLowerCase();
                    if (matchedUser.agencyName || matchedUser.agent_id || assignedRole === "agent") {
                        assignedRole = "agent";
                    } else {
                        assignedRole = assignedRole || "traveller";
                    }
                    matchedUser.role = assignedRole;
                    setActiveSession(matchedUser);
                    localStorage.setItem("travelverse_current_user_role", assignedRole);
                    const targetPage = (assignedRole === "agent") ? "agent-dashboard.html" : "dashboard.html";
                    window.location.href = targetPage;
                } else {
                    showToast("error", "Couldn't log you in", "The email/username or password you entered is incorrect.");
                }
            } finally {
                if (submitBtn) {
                    submitBtn.textContent = originalText;
                    submitBtn.disabled = false;
                }
            }
        });
    }

    // Enter key listener for custom Google email input
    const customGoogleEmailInput = document.getElementById("google-custom-email");
    if (customGoogleEmailInput) {
        customGoogleEmailInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                const email = customGoogleEmailInput.value.trim();
                if (email && email.includes("@")) {
                    handleGoogleAccountSelection(email);
                } else {
                    showToast("error", "Invalid Email", "Please enter a valid Google email address.");
                }
            }
        });
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAuth);
} else {
    initAuth();
}

// ===============================
// GOOGLE & APPLE SIGN-IN FLOW
// ===============================
// SOCIAL SIGN IN (GOOGLE & APPLE)
// ===============================
async function handleSocialSignIn(email, name = "") {
    const emailClean = (email || "").trim().toLowerCase();
    if (!emailClean) return;

    // 1. Check if user already exists in local storage accounts
    const accounts = getAccounts();
    let existingAccount = accounts.find(acc => acc && acc.email && acc.email.toLowerCase() === emailClean);

    if (existingAccount) {
        setActiveSession(existingAccount);
        const googleModal = document.getElementById("google-auth-modal");
        if (googleModal) googleModal.classList.remove("show");
        const isAgent = (existingAccount.role === "agent") || (window.CURRENT_ROLE === "agent") || !!existingAccount.agencyName;
        window.location.href = isAgent ? "agent-dashboard.html" : "dashboard.html";
        return;
    }

    // 2. Check if account exists on backend
    try {
        const res = await fetch(`${API_BASE}/all-users`);
        if (res.ok) {
            const data = await res.json();
            if (data.status === "success" && Array.isArray(data.users)) {
                const found = data.users.find(u => u && u.email && u.email.toLowerCase() === emailClean);
                if (found) {
                    const isAgent = (found.role === "agent") || (window.CURRENT_ROLE === "agent") || !!found.agency_name;
                    const userObj = {
                        firstName: found.first_name,
                        lastName: found.last_name,
                        username: found.username,
                        email: found.email,
                        password: found.password || "travel123",
                        role: isAgent ? "agent" : (found.role || "traveller"),
                        agencyName: found.agency_name || "",
                        agentName: found.agent_name || "",
                        badges: found.badges || [],
                        profilePic: found.profile_pic || ""
                    };
                    const accs = getAccounts();
                    accs.push(userObj);
                    saveAccounts(accs);
                    setActiveSession(userObj);

                    const googleModal = document.getElementById("google-auth-modal");
                    if (googleModal) googleModal.classList.remove("show");
                    window.location.href = isAgent ? "agent-dashboard.html" : "dashboard.html";
                    return;
                }
            }
        }
    } catch (e) {}

    // 3. Register new social account if it doesn't exist yet
    const isAgent = (window.CURRENT_ROLE === "agent");
    const role = isAgent ? "agent" : "traveller";
    const nameParts = (name || emailClean.split("@")[0]).trim().split(" ");
    const firstName = nameParts[0] || (isAgent ? "Agent" : "Traveler");
    const lastName = nameParts.slice(1).join(" ") || "";
    const username = emailClean.split("@")[0].replace(/[^a-zA-Z0-9]/g, "") || "traveler";

    const userObj = {
        firstName: firstName,
        lastName: lastName,
        username: username,
        email: emailClean,
        password: "social_oauth_password",
        role: role,
        agencyName: isAgent ? `${firstName}'s Agency` : "",
        agentName: isAgent ? `${firstName} ${lastName}`.trim() : "",
        badges: isAgent ? ["Verified Partner Agent"] : ["🎒 Backpacker"],
        profilePic: ""
    };

    try {
        await fetch(`${API_BASE}/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                first_name: firstName,
                last_name: lastName,
                username: username,
                email: emailClean,
                password: "social_oauth_password",
                role: role,
                agency_name: userObj.agencyName,
                agent_name: userObj.agentName,
                badges: userObj.badges
            })
        });
    } catch (err) {}

    const accs = getAccounts();
    const idx = accs.findIndex(a => a && a.email && a.email.toLowerCase() === emailClean);
    if (idx >= 0) accs[idx] = userObj; else accs.push(userObj);

    saveAccounts(accs);
    setActiveSession(userObj);

    const googleModal = document.getElementById("google-auth-modal");
    if (googleModal) googleModal.classList.remove("show");
    window.location.href = isAgent ? "agent-dashboard.html" : "dashboard.html";
}

function closeGoogleModal() {
    const googleModal = document.getElementById("google-auth-modal");
    if (googleModal) {
        googleModal.classList.remove("show");
        googleModal.style.setProperty("display", "none", "important");
        googleModal.style.setProperty("opacity", "0", "important");
        googleModal.style.setProperty("visibility", "hidden", "important");
        googleModal.style.setProperty("pointer-events", "none", "important");
    }
}

function openGoogleModal() {
    const googleModal = document.getElementById("google-auth-modal");
    const accountsList = document.getElementById("google-accounts-list");

    if (!googleModal) {
        console.error("google-auth-modal element not found");
        return;
    }

    let html = "";
    const localAccounts = getAccounts();

    // Custom default device accounts for realistic chooser feel
    const defaultAccounts = [
        { firstName: "Joreen", lastName: "Soller", email: "jsoller@gmail.com" },
        { firstName: "Alex", lastName: "Rivera", email: "alex.rivera@gmail.com" }
    ];

    const allAccountsMap = new Map();
    defaultAccounts.forEach(acc => allAccountsMap.set(acc.email.toLowerCase(), acc));
    if (localAccounts && Array.isArray(localAccounts)) {
        localAccounts.forEach(acc => {
            if (acc && acc.email) allAccountsMap.set(acc.email.toLowerCase(), acc);
        });
    }

    const uniqueAccounts = Array.from(allAccountsMap.values());

    uniqueAccounts.forEach(acc => {
        const name = (acc.firstName ? `${acc.firstName} ${acc.lastName || ''}`.trim() : acc.name) || 'Google User';
        const initial = (acc.firstName || acc.email || 'G')[0].toUpperCase();
        html += `
            <div class="google-acc-item" data-email="${acc.email}" data-name="${name}" onclick="handleGoogleAccountSelection('${acc.email}')" style="display:flex; align-items:center; gap:16px; padding:12px 14px; border-bottom:1px solid #dadce0; cursor:pointer; user-select:none; transition:background 0.15s ease;" onmouseover="this.style.background='#f8f9fa'" onmouseout="this.style.background='transparent'">
                <div style="width:36px; height:36px; border-radius:50%; background:#1a73e8; color:#fff; font-weight:500; display:flex; align-items:center; justify-content:center; font-size:15px; font-family:'Google Sans', Roboto, sans-serif; flex-shrink:0;">
                    ${initial}
                </div>
                <div style="flex:1; overflow:hidden;">
                    <div style="font-weight:500; font-size:14px; color:#202124; font-family:'Google Sans', Roboto, sans-serif; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${name}</div>
                    <div style="font-size:12.5px; color:#5f6368; font-family:Roboto, sans-serif; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${acc.email}</div>
                </div>
            </div>
        `;
    });

    if (accountsList) accountsList.innerHTML = html;
    
    // Hide custom input box initially
    const customBox = document.getElementById("google-custom-box");
    if (customBox) customBox.style.display = "none";

    googleModal.classList.add("show");
    googleModal.style.setProperty("display", "flex", "important");
    googleModal.style.setProperty("opacity", "1", "important");
    googleModal.style.setProperty("visibility", "visible", "important");
    googleModal.style.setProperty("pointer-events", "auto", "important");
    googleModal.style.setProperty("z-index", "999999", "important");
}

// Helper to toggle Reset Password modal steps
let resetResendTimer = null;
function startResetResendCountdown() {
    const resendBtn = document.getElementById("reset-resend-btn");
    const timerText = document.getElementById("reset-timer-text");
    if (!resendBtn) return;

    clearInterval(resetResendTimer);
    let secondsLeft = 30;
    resendBtn.style.pointerEvents = "none";
    resendBtn.style.opacity = "0.5";
    if (timerText) {
        timerText.style.display = "inline";
        timerText.textContent = `(${secondsLeft}s)`;
    }

    resetResendTimer = setInterval(() => {
        secondsLeft--;
        if (secondsLeft <= 0) {
            clearInterval(resetResendTimer);
            resendBtn.style.pointerEvents = "auto";
            resendBtn.style.opacity = "1";
            if (timerText) timerText.style.display = "none";
        } else {
            if (timerText) timerText.textContent = `(${secondsLeft}s)`;
        }
    }, 1000);
}

function switchResetModalStep(step) {
    const resetStep1 = document.getElementById("reset-step-1");
    const resetStep2 = document.getElementById("reset-step-2");
    const resetStep3 = document.getElementById("reset-step-3");
    const resetEmail = document.getElementById("reset-email");
    const resetDisplayEmail = document.getElementById("reset-display-email");
    const resetOtpInput = document.getElementById("reset-otp-input");
    const resetNewPassword = document.getElementById("reset-new-password");

    if (resetStep1) resetStep1.style.display = (step === 1) ? "block" : "none";
    if (resetStep2) resetStep2.style.display = (step === 2) ? "block" : "none";
    if (resetStep3) resetStep3.style.display = (step === 3) ? "block" : "none";

    if (step === 1) {
        clearInterval(resetResendTimer);
        if (resetEmail) resetEmail.focus();
    } else if (step === 2) {
        const emailVal = window._resetTargetEmail || (resetEmail ? resetEmail.value.trim() : "");
        if (resetDisplayEmail) resetDisplayEmail.textContent = emailVal;
        if (resetOtpInput) {
            resetOtpInput.value = "";
            resetOtpInput.focus();
        }
        startResetResendCountdown();
    } else if (step === 3) {
        clearInterval(resetResendTimer);
        if (resetNewPassword) {
            resetNewPassword.value = "";
            resetNewPassword.focus();
        }
        const confirmPw = document.getElementById("reset-confirm-password");
        if (confirmPw) confirmPw.value = "";
    }
}

async function handleGoogleAccountSelection(email) {
    if (!email || !email.includes("@")) {
        showToast("error", "Invalid Email", "Please enter a valid Google email address.");
        return;
    }

    closeGoogleModal();

    const loginForm = document.getElementById("login-form");
    if (loginForm && loginForm.classList.contains("active")) {
        handleSocialSignIn(email, "Google User");
        return;
    }

    const regEmailInput = document.getElementById("reg-email");
    if (regEmailInput) regEmailInput.value = email;

    try {
        // Pre-verify email on backend for signup
        await fetch(`${API_BASE}/send-signup-email-otp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email })
        });

        // Mark verified for signup
        await fetch(`${API_BASE}/verify-signup-email-otp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, otp: "000000" }) // backend auto-verifies
        });
    } catch (err) {
        console.warn("Backend pre-verify note:", err);
    }

    const signupStep1 = document.getElementById("signup-step1");
    const signupStep2 = document.getElementById("signup-step2");
    const stepIndicator = document.getElementById("step-indicator");
    const registerCopy = document.getElementById("register-copy");

    if (signupStep1) signupStep1.style.display = "none";
    if (signupStep2) signupStep2.style.display = "block";

    if (stepIndicator) stepIndicator.textContent = "Step 2 of 3";
    if (registerCopy) {
        const h2 = registerCopy.querySelector(".headline");
        const sub = registerCopy.querySelector(".sub");
        if (h2) h2.textContent = "Create your password";
        if (sub) sub.textContent = `Google email (${email}) verified! Set your account password.`;
    }

    showToast("success", "Google Verified!", `Email ${email} verified via Google. Please set your password.`);
}

window.openGoogleModal = openGoogleModal;
window.closeGoogleModal = closeGoogleModal;
window.handleGoogleAccountSelection = handleGoogleAccountSelection;

// ---------- Global Agent Modal Functions in auth.js ----------
if (typeof window.openAgentRegisterModal !== "function") {
    window.openAgentRegisterModal = function() {
        const modal = document.getElementById("agent-register-modal");
        if (modal) {
            modal.classList.add("show");
            modal.style.setProperty("display", "flex", "important");
            modal.style.setProperty("opacity", "1", "important");
            modal.style.setProperty("visibility", "visible", "important");
            modal.style.setProperty("pointer-events", "auto", "important");
            modal.style.setProperty("z-index", "9999999", "important");
        }
    };
}

if (typeof window.closeAgentRegisterModal !== "function") {
    window.closeAgentRegisterModal = function() {
        const modal = document.getElementById("agent-register-modal");
        if (modal) {
            modal.classList.remove("show");
            modal.style.setProperty("display", "none", "important");
            modal.style.setProperty("opacity", "0", "important");
            modal.style.setProperty("visibility", "hidden", "important");
            modal.style.setProperty("pointer-events", "none", "important");
        }
    };
}

if (typeof window.submitAgentFromModal !== "function") {
    window.submitAgentFromModal = function() {
        const completeBtn = document.getElementById("signup-complete-btn");
        if (completeBtn) {
            completeBtn.click();
        }
    };
}

// Bind explicit click on Open Agent Registration Form button
const openAgentBtn = document.getElementById("open-agent-popup-btn");
if (openAgentBtn) {
    openAgentBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        window.openAgentRegisterModal();
    });
}

// Backdrop click closes agent modal
const agentModalEl = document.getElementById("agent-register-modal");
if (agentModalEl) {
    agentModalEl.addEventListener("click", (e) => {
        if (e.target === agentModalEl) {
            window.closeAgentRegisterModal();
        }
    });
}

document.addEventListener("click", async (e) => {
    // Open Agent Registration Modal Button Click
    if (e.target.closest("#open-agent-popup-btn")) {
        e.preventDefault();
        e.stopPropagation();
        window.openAgentRegisterModal();
        return;
    }

    // Close Agent Registration Modal
    if (e.target.closest("#agent-register-modal .close-btn, #agent-register-modal [onclick*='closeAgentRegisterModal']")) {
        e.preventDefault();
        window.closeAgentRegisterModal();
        return;
    }

    // Continue with Google Button Click (Sign Up Step 1 OTP Bypass)
    if (e.target.closest(".google-auth-btn, #signup-google-quick-btn")) {
        e.preventDefault();
        openGoogleModal();
        return;
    }

    if (e.target.closest(".apple-auth-btn")) {
        e.preventDefault();
        handleSocialSignIn("apple.user@icloud.com", "Apple Traveler");
        return;
    }

    // Google Modal Close
    if (e.target.closest("#google-auth-close")) {
        closeGoogleModal();
        return;
    }

    // Google Account Choice Item Clicked
    const accItem = e.target.closest(".google-acc-item");
    if (accItem) {
        const email = accItem.dataset.email;
        const name = accItem.dataset.name;
        handleGoogleAccountSelection(email, name);
        return;
    }

    // Google Use Another Account Clicked
    if (e.target.closest("#google-use-another-btn")) {
        const customBox = document.getElementById("google-custom-box");
        if (customBox) {
            const isHidden = customBox.style.display === "none" || !customBox.style.display;
            customBox.style.display = isHidden ? "block" : "none";
            const input = document.getElementById("google-custom-email");
            if (isHidden && input) input.focus();
        }
        return;
    }

    // Google Custom Email Submit Clicked
    if (e.target.closest("#google-custom-submit")) {
        const input = document.getElementById("google-custom-email");
        const email = input ? input.value.trim() : "";
        if (email && email.includes("@")) {
            handleGoogleAccountSelection(email);
        } else {
            showToast("error", "Invalid Email", "Please enter a valid Google email address.");
        }
        return;
    }

    // Open Reset Password Modal
    const link = e.target.closest("#forgot-password-link, a[href='#forgot']");
    const isForgotLink = link || (e.target.tagName === 'A' && e.target.textContent && e.target.textContent.toLowerCase().includes("forgot"));

    if (isForgotLink) {
        e.preventDefault();
        const loginEmailInput = document.getElementById("login-email");
        const resetEmail = document.getElementById("reset-email");
        const resetOtpInput = document.getElementById("reset-otp-input");
        const resetNewPassword = document.getElementById("reset-new-password");
        const resetConfirmPassword = document.getElementById("reset-confirm-password");
        const resetPasswordModal = document.getElementById("reset-password-modal");

        const defaultEmail = loginEmailInput ? loginEmailInput.value.trim() : "";
        if (resetEmail) resetEmail.value = defaultEmail;
        if (resetOtpInput) resetOtpInput.value = "";
        if (resetNewPassword) resetNewPassword.value = "";
        if (resetConfirmPassword) resetConfirmPassword.value = "";

        switchResetModalStep(1);

        if (resetPasswordModal) resetPasswordModal.classList.add("show");
        return;
    }

    // Close Reset Password Modal
    if (e.target.closest("#reset-password-close, #reset-password-cancel")) {
        const resetPasswordModal = document.getElementById("reset-password-modal");
        if (resetPasswordModal) resetPasswordModal.classList.remove("show");
        return;
    }

    // Change Email Link (Back to Step 1)
    if (e.target.closest("#reset-change-email")) {
        e.preventDefault();
        switchResetModalStep(1);
        return;
    }

    // Resend Code Button
    if (e.target.closest("#reset-resend-btn")) {
        e.preventDefault();
        const resendBtn = document.getElementById("reset-resend-btn");
        if (resendBtn && resendBtn.style.pointerEvents === "none") return;

        const email = window._resetTargetEmail || (document.getElementById("reset-email") ? document.getElementById("reset-email").value.trim().toLowerCase() : "");
        if (!email) return;

        if (resendBtn) resendBtn.textContent = "Sending…";
        fetch(`${API_BASE}/send-otp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email })
        })
        .then(async (res) => {
            const data = await res.json();
            if (res.ok) {
                showToast("success", "Code Resent", `A new 6-digit code has been sent to ${email}. Check your inbox!`);
                startResetResendCountdown();
            } else {
                showToast("error", "Note", data.detail || data.message || "Could not resend code yet.");
            }
        })
        .catch(() => {
            showToast("error", "Connection Error", "Could not resend code. Please try again.");
        })
        .finally(() => {
            if (resendBtn) resendBtn.textContent = "Resend Code";
        });
        return;
    }

    // Step 1: Send OTP Button
    if (e.target.closest("#reset-send-otp-btn")) {
        const btn = e.target.closest("#reset-send-otp-btn");
        if (btn.disabled || btn.dataset.busy === "true") return;

        const resetEmail = document.getElementById("reset-email");
        const email = resetEmail ? resetEmail.value.trim().toLowerCase() : "";
        if (!email || !email.includes("@")) {
            showToast("error", "Invalid email", "Please enter a valid registered email address.");
            return;
        }

        btn.dataset.busy = "true";
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = "Sending Code…";

        fetch(`${API_BASE}/send-otp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email })
        })
        .then(async (response) => {
            const data = await response.json();
            if (!response.ok) {
                showToast("error", "Account Not Found", data.detail || "No account registered with this email address.");
                return;
            }
            window._resetTargetEmail = email;
            switchResetModalStep(2);
            showToast("success", "Code Sent", `A 6-digit verification code has been sent to ${email}. Check your Gmail inbox!`);
        })
        .catch((err) => {
            console.warn("Error calling send-otp:", err);
            showToast("error", "Connection Error", "Could not send verification code. Please ensure the backend server is running.");
        })
        .finally(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            delete btn.dataset.busy;
        });
        return;
    }

    // Step 2: Verify OTP Only Button
    if (e.target.closest("#reset-verify-otp-btn")) {
        const btn = e.target.closest("#reset-verify-otp-btn");
        if (btn.disabled || btn.dataset.busy === "true") return;

        const resetOtpInput = document.getElementById("reset-otp-input");
        const enteredOtp = resetOtpInput ? resetOtpInput.value.trim() : "";
        const email = window._resetTargetEmail || (document.getElementById("reset-email") ? document.getElementById("reset-email").value.trim().toLowerCase() : "");

        if (!enteredOtp || enteredOtp.length !== 6) {
            showToast("error", "Invalid Code", "Please enter the complete 6-digit OTP code.");
            return;
        }

        btn.dataset.busy = "true";
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = "Verifying…";

        fetch(`${API_BASE}/verify-otp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: email,
                otp: enteredOtp
            })
        })
        .then(async (response) => {
            const data = await response.json();
            if (!response.ok) {
                showToast("error", "Verification Failed", data.detail || "Invalid OTP code. Please check your email.");
                return;
            }
            window._verifiedOtp = enteredOtp;
            showToast("success", "OTP Verified", "Code verified! Now enter your new password.");
            switchResetModalStep(3);
        })
        .catch((err) => {
            console.warn("Error verifying OTP:", err);
            showToast("error", "Connection Error", "Could not verify code. Please check your backend.");
        })
        .finally(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            delete btn.dataset.busy;
        });
        return;
    }

    // Step 3: Save New Password Button
    if (e.target.closest("#reset-password-save")) {
        const btn = e.target.closest("#reset-password-save");
        if (btn.disabled || btn.dataset.busy === "true") return;

        const resetNewPassword = document.getElementById("reset-new-password");
        const resetConfirmPassword = document.getElementById("reset-confirm-password");

        const enteredEmail = window._resetTargetEmail || (document.getElementById("reset-email") ? document.getElementById("reset-email").value.trim().toLowerCase() : "");
        const verifiedOtp = window._verifiedOtp || "";
        const newPw = resetNewPassword ? resetNewPassword.value : "";
        const confirmPw = resetConfirmPassword ? resetConfirmPassword.value : "";

        if (!enteredEmail || !enteredEmail.includes("@")) {
            showToast("error", "Email Missing", "Please restart password recovery.");
            return;
        }
        if (!newPw || newPw.length < 6) {
            showToast("error", "Weak Password", "Please enter a new password of at least 6 characters.");
            return;
        }
        if (newPw !== confirmPw) {
            showToast("error", "Passwords Mismatch", "Passwords do not match. Please re-enter.");
            return;
        }

        btn.dataset.busy = "true";
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = "Updating Password…";

        fetch(`${API_BASE}/reset-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: enteredEmail,
                otp: verifiedOtp,
                new_password: newPw
            })
        })
        .then(async (response) => {
            const data = await response.json();
            if (!response.ok) {
                showToast("error", "Reset Failed", data.detail || "Could not reset password. Please request a new OTP.");
                return;
            }

            const accounts = getAccounts();
            if (enteredEmail) {
                const user = accounts.find(acc => acc.email.toLowerCase() === enteredEmail.toLowerCase());
                if (user) {
                    user.password = newPw;
                    saveAccounts(accounts);
                }
            }

            const resetPasswordModal = document.getElementById("reset-password-modal");
            if (resetPasswordModal) resetPasswordModal.classList.remove("show");

            showToast("success", "Password Updated", "Your password has been changed! You can now log in.");
            
            setTimeout(() => {
                if (typeof showTab === "function") showTab("login");
                const loginEmail = document.getElementById("login-email");
                if (loginEmail && enteredEmail) loginEmail.value = enteredEmail;
                const loginPw = document.getElementById("login-password");
                if (loginPw) {
                    loginPw.value = "";
                    loginPw.focus();
                }
            }, 800);
        })
        .catch((err) => {
            console.warn("Error resetting password:", err);
            showToast("error", "Connection Error", "Could not reset password. Please ensure the backend server is running.");
        })
        .finally(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            delete btn.dataset.busy;
        });
        return;
    }
});