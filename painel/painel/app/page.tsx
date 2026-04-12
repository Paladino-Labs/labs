"use client";

import { useEffect, useState } from "react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // 🔐 Redireciona se já estiver logado
  useEffect(() => {
    const token = localStorage.getItem("token");

    if (token) {
      window.location.href = "/dashboard";
    }
  }, []);

  async function handleLogin() {
    const response = await fetch("http://127.0.0.1:8000/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json();

    if (data.access_token) {
      localStorage.setItem("token", data.access_token);
      window.location.href = "/dashboard";
    } else {
      alert("Usuário ou senha inválidos");
    }
  }

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="p-6 border rounded w-80">
        <h1 className="text-xl mb-4">Login</h1>

        <input
          className="border p-2 w-full mb-2"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <input
          type="password"
          className="border p-2 w-full mb-4"
          placeholder="Senha"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button
          onClick={handleLogin}
          className="bg-black text-white w-full p-2"
        >
          Entrar
        </button>
      </div>
    </div>
  );
}