# Space Invaders — Multiplayer
## Trabalho final de ATR

Clone do clássico *Space Invaders* para **dois jogadores no mesmo teclado**,
reescrito sobre uma **arquitetura desacoplada** com um núcleo de simulação puro
(sem `turtle`, sem threads) e uma camada de renderização fina isolada.

### Jogabilidade

Duas naves cooperam para destruir a formação de invasores antes que ela alcance
a base. Cada acerto vale pontos; cada jogador tem suas próprias vidas.

| Ação      | Jogador 1 (WASD) | Jogador 2 (setas) |
|-----------|------------------|-------------------|
| Cima      | `W`              | `↑`               |
| Esquerda  | `A`              | `←`               |
| Baixo     | `S`              | `↓`               |
| Direita   | `D`              | `→`               |
| Atirar    | `Espaço`         | `Enter`           |

### Como executar

O jogo precisa de um display gráfico e do módulo `tkinter` (pacote
`python3-tk` na maioria das distribuições). O núcleo não tem dependências
além da biblioteca padrão.

```bash
cd newSpaceInvaders
python3 -m spaceinvaders        # abre a janela do jogo (2 jogadores)
```

### Arquitetura (desacoplada por camadas)

O código vive no pacote `spaceinvaders/`. Cada camada depende apenas das
camadas abaixo dela — a lógica do jogo **não conhece** teclado nem tela:

```
config.py     parâmetros imutáveis (tamanhos, velocidades, formação)
geometry.py   clamp + colisão AABB (sem dependências)
input.py      Intent + mapas de teclas (WASD / setas) + InputState
entities.py   Player / Enemy / Bullet — dados + regras locais, nada de I/O
world.py      GameWorld: simulação determinística, um passo por quadro
engine.py     GameLoop.tick(dt) + run_headless() — dirige o mundo sem tela
renderer.py   interface Renderer + NullRenderer (execução sem display)
turtle_app.py única camada que importa `turtle` (tela, teclas, ontimer)
```

Pontos de projeto:

- **Desempenho:** um único laço de tempo fixo na thread principal
  (`screen.ontimer`), estado em listas simples e entrada por conjuntos
  (`set`) O(1). Não há thread nem semáforo por entidade (como na versão
  antiga) — nada de contenção nem `pickle`.
- **Determinismo/testabilidade:** o RNG é injetado em `GameWorld`, e o mundo
  avança por `dt` explícito. Assim a simulação inteira roda *headless* em
  testes via `run_headless()`.
- **Renderização isolada:** o mundo expõe `snapshot()` (um `dict` simples); o
  renderer desenha a partir disso e nunca toca nos objetos internos.

### Testes

Testes unitários com `pytest`; cobertura medida sobre o núcleo (o backend
`turtle_app.py` é excluído porque exige display).

```bash
cd newSpaceInvaders
python3 -m pip install -r requirements-dev.txt
python3 -m pytest --cov --cov-report=term-missing
```

O núcleo está com **100% de cobertura** (meta do trabalho: ≥ 90%).

### Código legado

Os arquivos `game.py`, `Enemy.py`, `Player.py`, `Disparo.py`, `Score.py`,
`testes.py`, `constants.py` e `logServer.py` são a **implementação original**
(modelo thread-por-entidade + `turtle`) e foram mantidos apenas como registro
histórico do trabalho. A versão viável e testada é o pacote `spaceinvaders/`.
