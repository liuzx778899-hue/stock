<template>
  <div class="app">
    <aside class="sidebar">
      <div class="logo">
        <h1>A-Stock System</h1>
      </div>
      <nav class="nav">
        <router-link to="/" class="nav-item" active-class="active">
          <span class="icon">📊</span>
          <span>Dashboard</span>
        </router-link>
        <router-link to="/collector" class="nav-item" active-class="active">
          <span class="icon">📥</span>
          <span>Collector</span>
        </router-link>
        <router-link to="/settings" class="nav-item" active-class="active">
          <span class="icon">⚙️</span>
          <span>Settings</span>
        </router-link>
      </nav>
    </aside>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
</script>