# Space Invaders
## Trabalho final de ATR
### Introdução
Space Invaders é e um jogo de arcade criado em 1978 por Tomohiro Nishikado e licenciado pela Taito Corporation. Trata-se de um dos primeiros jogos de tiro com gráficos em duas dimensões, inspirado em obras como Guerra dos Mundos e Star Wars. O objetivo principal do jogo é impedir uma invasão de naves alienígenas, utilizando uma arma terráquea para fazer a maior pontuação possível.

Para fazer a programação deste jogo foram utilizado conceitos de automação em tempo real, incluindo threads com dispositivos para controlarem problemas ocorridos em programação concorrente.

Além disso, como o logger poderia ficar em outra máquina, foi necessário utilizar de um socket para realizar a parte da comunicação.
### Objetivo
O objetivo deste trabalho é programar um jogo inspirado no game clássico  “Space Invaders”. Neste programa o jogador controla uma nave e tem como objetivo destruir as naves inimigas e desviar dos ataques provenientes das mesmas.

O jogo possui diversas fases sendo que a dificuldade aumenta conforme o usuário for passando por elas. Para controlar a nave o usuário utiliza o teclado enquanto visualiza uma tela gráfica semelhante a imagem abaixo.

### Instalação
Por questãoes de praticidade indica se a utilização de do pacote de gestão de ambiente da aplicação o `python3 -m pip3 install venv` dessa forma garante se a estabilidade da aplicação para o ambiente do usuário.

Existe um descritivo de ambiente colocado como `requirements.txt` utilizado pelo `pip3
 para descrever o ambiente da aplicação durante a instanciação do amviente virtual.
 
````
# intalaçao do python 3 -- a versão utilizada no trabalho foi a 3.6
sudo apt install python3 pip3
# instalaçao do venv
python3 -m pip3 install venv
# instalaçao dos requirements
pip3 install -r requirements.txt

python3 git game.py
