/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ["class"],
    content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./src/styles/**/*.css",
  ],
  theme: {
  	extend: {
  		fontFamily: {
  			sans: [
  				'DM Sans',
  				'ui-sans-serif',
  				'-apple-system',
  				'system-ui',
  				'Segoe UI',
  				'Helvetica',
  				'sans-serif'
  			],
  			mono: [
  				'ui-monospace',
  				'Menlo',
  				'Monaco',
  				'Consolas',
  				'monospace'
  			]
  		},
  		colors: {
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		},
  		animation: {
  			scroll: 'scroll 40s linear infinite',
  			'slide-left': 'slide-left 55s linear infinite',
  			'fade-in': 'fade-in 300ms ease-out',
  			'slide-up': 'slide-up 300ms ease-out',
  			'scale-in': 'scale-in 150ms ease-out',
  			shimmer: 'shimmer 2s linear infinite',
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		},
  		keyframes: {
  			scroll: {
  				'0%': {
  					transform: 'translateX(0)'
  				},
  				'100%': {
  					transform: 'translateX(calc(-250px * 14))'
  				}
  			},
  			'slide-left': {
  				from: {
  					transform: 'translateX(0)'
  				},
  				to: {
  					transform: 'translateX(-100%)'
  				}
  			},
  			carousel: {
  				'0%': {
  					transform: 'translateX(0)'
  				},
  				'100%': {
  					transform: 'translateX(-50%)'
  				}
  			},
  			'fade-in': {
  				from: {
  					opacity: '0'
  				},
  				to: {
  					opacity: '1'
  				}
  			},
  			'slide-up': {
  				from: {
  					transform: 'translateY(10px)',
  					opacity: '0'
  				},
  				to: {
  					transform: 'translateY(0)',
  					opacity: '1'
  				}
  			},
  			'scale-in': {
  				from: {
  					transform: 'scale(0.95)',
  					opacity: '0'
  				},
  				to: {
  					transform: 'scale(1)',
  					opacity: '1'
  				}
  			},
  			shimmer: {
  				'0%': {
  					backgroundPosition: '-1000px 0'
  				},
  				'100%': {
  					backgroundPosition: '1000px 0'
  				}
  			},
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		},
  		transitionTimingFunction: {
  			'snap-ease': 'cubic-bezier(0.45, 0.05, 0.55, 0.95)',
  			spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)'
  		},
  		transitionDuration: {
  			'150': '150ms',
  			'300': '300ms',
  			'500': '500ms',
  			'800': '800ms'
  		},
  		boxShadow: {
  			sm: '0 1px 2px 0 rgba(155, 126, 189, 0.05)',
  			DEFAULT: '0 1px 3px 0 rgba(155, 126, 189, 0.1), 0 1px 2px -1px rgba(155, 126, 189, 0.1)',
  			md: '0 4px 6px -1px rgba(155, 126, 189, 0.1), 0 2px 4px -2px rgba(155, 126, 189, 0.1)',
  			lg: '0 10px 15px -3px rgba(155, 126, 189, 0.1), 0 4px 6px -4px rgba(155, 126, 189, 0.1)',
  			xl: '0 20px 25px -5px rgba(155, 126, 189, 0.1), 0 8px 10px -6px rgba(155, 126, 189, 0.1)',
  			'2xl': '0 25px 50px -12px rgba(155, 126, 189, 0.25)',
  			inner: 'inset 0 2px 4px 0 rgba(155, 126, 189, 0.05)',
  			'purple-glow': '0 0 20px rgba(155, 126, 189, 0.3)',
  			'purple-glow-lg': '0 0 40px rgba(155, 126, 189, 0.6)'
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};
