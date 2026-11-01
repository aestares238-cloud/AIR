# Login and Navbar Implementation

This document describes the implementation of a basic authentication flow and navigation bar for the control panel.

## Authentication
1. **Login Page (`templates/pages/login.html`)**
   - Create a basic HTML form requiring a username/password.
   - If using Supabase, we can utilize Supabase Auth to handle secure authentication and JWT tokens.

2. **Backend Authentication**
   - Add FastAPI dependencies to verify the session token (JWT) on protected routes.
   - Store the user's session in a secure HTTP-only cookie or Local Storage in the browser.

## Navbar Integration
1. **Global Navigation Bar**
   - Create a persistent top navigation bar or sidebar across all pages.
   - Include links to the available modules:
     - Dashboard (`/pages/dashboard`)
     - Real-Time Graphs (`/pages/real_time_graphs`)
     - AI Setup (`/pages/ai_setup`)
     - Contacts (`/pages/contacts`)
     - Alerts (`/pages/alerts`)
     - Traccar Setup (`/pages/traccar_setup`)
     - AC Setup (`/pages/ac_setup`)

2. **Styling and State**
   - Ensure the navbar highlights the currently active page.
   - Add a "Logout" button on the navbar that clears the session and redirects to the login page.
