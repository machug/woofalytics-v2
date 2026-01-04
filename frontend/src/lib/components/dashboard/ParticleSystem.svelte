<script lang="ts">
	import { lastBark, sessionBarkCount, type BarkEvent } from '$lib/stores/bark';

	interface Props {
		width?: number;
		height?: number;
	}

	let { width = 400, height = 300 }: Props = $props();

	let canvas: HTMLCanvasElement;
	let ctx: CanvasRenderingContext2D | null = null;
	let animationFrame: number;

	interface Particle {
		x: number;
		y: number;
		vx: number;
		vy: number;
		life: number;
		maxLife: number;
		size: number;
		hue: number;
		saturation: number;
		lightness: number;
		type: 'spark' | 'bone';
		rotation?: number;
		rotationSpeed?: number;
	}

	let particles = $state<Particle[]>([]);
	let lastBarkId: string | null = null;

	// Bone emoji for special particles
	const BONE_EMOJI = '🦴';

	function createParticles(x: number, y: number, count: number, isSpecial: boolean) {
		const newParticles: Particle[] = [];
		for (let i = 0; i < count; i++) {
			const angle = (Math.PI * 2 * i) / count + Math.random() * 0.5;
			const speed = 2 + Math.random() * 4;
			const isBone = isSpecial && i % 5 === 0; // Every 5th particle is a bone in special mode

			newParticles.push({
				x,
				y,
				vx: Math.cos(angle) * speed,
				vy: Math.sin(angle) * speed - 2, // Bias upward
				life: 1,
				maxLife: 60 + Math.random() * 40,
				size: isBone ? 20 : 3 + Math.random() * 4,
				hue: isSpecial ? 45 : 180 + Math.random() * 40, // Gold for special, teal for normal
				saturation: 80 + Math.random() * 20,
				lightness: 50 + Math.random() * 20,
				type: isBone ? 'bone' : 'spark',
				rotation: isBone ? Math.random() * Math.PI * 2 : undefined,
				rotationSpeed: isBone ? (Math.random() - 0.5) * 0.2 : undefined
			});
		}
		// Reassign to trigger reactivity
		particles = [...particles, ...newParticles];
	}

	function updateParticles() {
		const gravity = 0.08;
		const friction = 0.98;

		particles = particles.filter((p) => {
			// Update physics
			p.vy += gravity;
			p.vx *= friction;
			p.vy *= friction;
			p.x += p.vx;
			p.y += p.vy;

			// Update life
			p.life -= 1 / p.maxLife;

			// Update rotation for bones
			if (p.rotation !== undefined && p.rotationSpeed !== undefined) {
				p.rotation += p.rotationSpeed;
			}

			return p.life > 0;
		});
	}

	function drawParticles() {
		if (!ctx) return;

		for (const p of particles) {
			ctx.save();

			if (p.type === 'bone') {
				// Draw bone emoji
				ctx.globalAlpha = p.life;
				ctx.translate(p.x, p.y);
				if (p.rotation !== undefined) {
					ctx.rotate(p.rotation);
				}
				ctx.font = `${p.size}px serif`;
				ctx.textAlign = 'center';
				ctx.textBaseline = 'middle';
				ctx.fillText(BONE_EMOJI, 0, 0);
			} else {
				// Draw spark particle
				const alpha = p.life * 0.8;
				ctx.globalAlpha = alpha;

				// Glow effect
				ctx.shadowColor = `hsla(${p.hue}, ${p.saturation}%, ${p.lightness}%, 0.8)`;
				ctx.shadowBlur = 10;

				ctx.fillStyle = `hsla(${p.hue}, ${p.saturation}%, ${p.lightness}%, ${alpha})`;
				ctx.beginPath();
				ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
				ctx.fill();
			}

			ctx.restore();
		}
	}

	function draw() {
		if (!ctx || !canvas) return;

		const dpr = window.devicePixelRatio || 1;
		const w = canvas.width / dpr;
		const h = canvas.height / dpr;

		// Clear canvas
		ctx.clearRect(0, 0, w, h);

		// Update and draw particles
		updateParticles();
		drawParticles();

		animationFrame = requestAnimationFrame(draw);
	}

	function setupCanvas() {
		if (!canvas) return;

		const dpr = window.devicePixelRatio || 1;
		canvas.width = width * dpr;
		canvas.height = height * dpr;

		ctx = canvas.getContext('2d');
		if (ctx) {
			ctx.scale(dpr, dpr);
		}
	}

	function triggerBarkEffect(bark: BarkEvent, barkCount: number) {
		if (!canvas) return;

		// Random position in canvas
		const x = 50 + Math.random() * (width - 100);
		const y = 50 + Math.random() * (height - 100);

		// Every 10th bark is special (golden bones)
		const isSpecial = barkCount % 10 === 0;

		// More particles for higher confidence
		const particleCount = Math.floor(20 + bark.confidence * 30);

		createParticles(x, y, isSpecial ? particleCount * 1.5 : particleCount, isSpecial);
	}

	// Derived bark count for display
	let barkCount = $derived($sessionBarkCount);

	// Setup canvas and animation loop
	$effect(() => {
		if (canvas && width > 0 && height > 0) {
			setupCanvas();
			animationFrame = requestAnimationFrame(draw);

			return () => {
				if (animationFrame) {
					cancelAnimationFrame(animationFrame);
				}
			};
		}
	});

	// Watch for new barks
	$effect(() => {
		const bark = $lastBark;
		const count = $sessionBarkCount;

		if (bark && bark.id !== lastBarkId) {
			lastBarkId = bark.id;
			triggerBarkEffect(bark, count);
		}
	});
</script>

<div class="particle-container">
	<canvas bind:this={canvas} style="width: {width}px; height: {height}px"></canvas>
	{#if particles.length === 0}
		<div class="empty-state">
			<span class="emoji">🐕</span>
			{#if barkCount > 0}
				<span class="bark-count">{barkCount} bark{barkCount === 1 ? '' : 's'} this session</span>
			{:else}
				<span class="text">Waiting for barks...</span>
			{/if}
		</div>
	{/if}
	{#if barkCount > 0}
		<div class="session-counter">
			<span class="counter-value">{barkCount}</span>
		</div>
	{/if}
</div>

<style>
	.particle-container {
		position: relative;
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	canvas {
		display: block;
	}

	.empty-state {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		pointer-events: none;
	}

	.emoji {
		font-size: 3rem;
		opacity: 0.3;
		animation: pulse 2s ease-in-out infinite;
	}

	.text {
		font-size: 0.875rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}

	.bark-count {
		font-size: 0.875rem;
		color: var(--accent-teal);
		font-weight: 600;
	}

	.session-counter {
		position: absolute;
		top: var(--space-sm);
		right: var(--space-sm);
		background: var(--bg-overlay);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		padding: var(--space-xs) var(--space-sm);
	}

	.counter-value {
		font-size: 0.75rem;
		font-weight: 700;
		font-family: 'JetBrains Mono', monospace;
		color: var(--accent-teal);
	}

	@keyframes pulse {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.1);
		}
	}
</style>
