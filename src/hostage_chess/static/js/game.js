/**
 * Hostage Chess game page.
 *
 * Renders the board with chessboard.js and only offers the moves, drops, and exchanges the
 * server lists as legal. Also runs the clocks and polls for the opponent's moves. The server
 * checks every action again before saving it.
 */

/* global Chessboard, $ */

(() => {
    "use strict";

    const POLL_INTERVAL_MS = 1500;
    const PIECE_NAMES = {p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king"};

    // The view the server built for this player (see `_game_view` in app.py).
    let cfg = window.GAME_CONFIG;
    let board = null;
    let legalMoveMap = {};
    let timerInterval = null;
    let pollInterval = null;

    // The drop or exchange in progress, or null:
    //   {type: "drop", airfieldIdx: 0}
    //   {type: "exchange", option: null}  (option is set once the player picks one)
    let mode = null;

    const exchangeDialog = document.getElementById("exchange-modal");
    const promotionDialog = document.getElementById("promotion-modal");

    // Helpers

    const pieceName = (piece) => PIECE_NAMES[piece.toLowerCase()];

    function pieceImage(piece, alt) {
        const colour = piece === piece.toUpperCase() ? "w" : "b";
        const img = document.createElement("img");
        img.src = `/static/img/Chess_Pieces_Sprite.svg#${colour}${piece.toUpperCase()}`;
        img.alt = alt;
        return img;
    }

    function highlightSquares(squares, className) {
        squares.forEach((square) => {
            document.querySelector(`#myBoard [data-square="${square}"]`).classList.add(className);
        });
    }

    function clearHighlights() {
        document.querySelectorAll(".highlight-legal, .highlight-drop").forEach((el) => {
            el.classList.remove("highlight-legal", "highlight-drop");
        });
    }

    function buildLegalMoveMap() {
        legalMoveMap = {};
        cfg.legalMoves.forEach((move) => {
            (legalMoveMap[move.from] ??= []).push(move);
        });
    }

    // Status and controls

    function setStatus(text, isError = false) {
        const status = document.getElementById("status-text");
        status.textContent = text;
        status.classList.toggle("active", cfg.isMyTurn && !isError);
        status.classList.toggle("waiting", !cfg.isMyTurn && !isError);
        status.classList.toggle("error", isError);
    }

    function showTurnStatus() {
        if (!cfg.isMyTurn) {
            setStatus("Opponent's turn");
        } else {
            setStatus(cfg.inCheck ? "Your turn, you are in check" : "Your turn");
        }
    }

    function updateControls() {
        const dropBtn = document.getElementById("btn-drop");
        const exchangeBtn = document.getElementById("btn-exchange");

        dropBtn.disabled = !cfg.isMyTurn || cfg.dropMoves.length === 0;
        exchangeBtn.disabled = !cfg.isMyTurn || cfg.exchangeOptions.length === 0;
        dropBtn.textContent = mode?.type === "drop" ? "Cancel Drop" : "Drop Piece";
        exchangeBtn.textContent = mode?.type === "exchange" ? "Cancel Exchange" : "Exchange Hostage";

        document.getElementById("white-timer").classList.toggle("timer-active", cfg.turn === "w");
        document.getElementById("black-timer").classList.toggle("timer-active", cfg.turn === "b");
    }

    // Clocks

    function formatTime(seconds) {
        return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    }

    function showTimes() {
        document.getElementById("whiteTime").textContent = formatTime(cfg.whiteTime);
        document.getElementById("blackTime").textContent = formatTime(cfg.blackTime);
    }

    function startTimer() {
        clearInterval(timerInterval);
        showTimes();
        timerInterval = setInterval(() => {
            const key = cfg.turn === "w" ? "whiteTime" : "blackTime";
            cfg[key] = Math.max(0, cfg[key] - 1);
            showTimes();
            if (cfg[key] === 0) {
                clearInterval(timerInterval);
                // Either player can report this; the server checks the clock before ending the game.
                sendTimeout(cfg.turnNo);
            }
        }, 1000);
    }

    // Board moves

    function initBoard() {
        board = Chessboard("myBoard", {
            position: cfg.boardFen,
            orientation: cfg.role,
            draggable: true,
            dropOffBoard: "snapback",
            pieceTheme: "/static/img/Chess_Pieces_Sprite.svg#{piece}",
            onDragStart,
            onDrop,
            onMouseoverSquare,
            onMouseoutSquare,
        });
        $(window).on("resize", () => board.resize());
    }

    function onDragStart(source) {
        // The server only lists moves for the player to move, and only from their own pieces.
        return cfg.isMyTurn && mode === null && Boolean(legalMoveMap[source]);
    }

    function onDrop(source, target) {
        clearHighlights();
        const matching = (legalMoveMap[source] || []).filter((move) => move.to === target);
        if (matching.length === 0) return "snapback";

        if (matching[0].promotion) {
            showPromotionDialog(matching);
            return; // Leave the pawn on the last rank while the player picks a piece
        }
        submitAction("/api/move", {from: source, to: target, promotion: null});
    }

    function onMouseoverSquare(square) {
        if (!cfg.isMyTurn || mode !== null || !legalMoveMap[square]) return;
        highlightSquares(
            legalMoveMap[square].map((move) => move.to),
            "highlight-legal"
        );
    }

    function onMouseoutSquare() {
        if (mode === null) clearHighlights();
    }

    // Promotion

    // `moves` are the legal moves to the last rank, one for each piece the pawn can become.
    function showPromotionDialog(moves) {
        const container = document.getElementById("promotion-options");
        container.replaceChildren();

        moves.forEach((move) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "promotion-btn";
            btn.setAttribute("aria-label", `Promote to ${pieceName(move.promotion)}`);
            btn.appendChild(pieceImage(move.promotion, ""));
            btn.addEventListener("click", () => {
                promotionDialog.close("chosen");
                submitAction("/api/move", move);
            });
            container.appendChild(btn);
        });

        promotionDialog.returnValue = "";
        promotionDialog.showModal();
    }

    // Closing the dialog without choosing a piece puts the pawn back
    function onPromotionClose() {
        if (promotionDialog.returnValue !== "chosen") board.position(cfg.boardFen, false);
    }

    // Prison and airfield trays

    function renderTrays() {
        const hostages = cfg.hostageState;
        renderTray("player-airfield", hostages.playerAirfield, cfg.isMyTurn && cfg.dropMoves.length > 0);
        renderTray("player-prison", hostages.playerPrison, false);
        renderTray("opponent-airfield", hostages.opponentAirfield, false);
        renderTray("opponent-prison", hostages.opponentPrison, false);
    }

    function renderTray(elementId, pieces, droppable) {
        const tray = document.getElementById(elementId);
        tray.replaceChildren();

        pieces.forEach((piece, idx) => {
            const img = pieceImage(piece, pieceName(piece));
            img.className = "tray-piece";

            if (droppable) {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "tray-piece-btn";
                btn.setAttribute("aria-label", `Drop ${pieceName(piece)}`);
                img.alt = "";
                btn.appendChild(img);
                btn.addEventListener("click", () => toggleDrop(idx));
                tray.appendChild(btn);
            } else {
                tray.appendChild(img);
            }
        });
    }

    // Drops and exchanges

    function cancelMode() {
        mode = null;
        clearHighlights();
        if (exchangeDialog.open) exchangeDialog.close();
        document.querySelectorAll(".tray-piece-btn.selected").forEach((el) => {
            el.classList.remove("selected");
        });
        updateControls();
        showTurnStatus();
    }

    function toggleDrop(airfieldIdx) {
        const wasSelected = mode?.type === "drop" && mode.airfieldIdx === airfieldIdx;
        cancelMode();
        if (wasSelected) return;

        mode = {type: "drop", airfieldIdx};
        document.querySelectorAll("#player-airfield .tray-piece-btn")[airfieldIdx].classList.add("selected");

        highlightSquares(
            cfg.dropMoves.filter((drop) => drop.airfieldIdx === airfieldIdx).map((drop) => drop.to),
            "highlight-drop"
        );
        updateControls();
        setStatus(`Click a highlighted square to drop your ${pieceName(cfg.hostageState.playerAirfield[airfieldIdx])}`);
    }

    function startExchange() {
        cancelMode();
        mode = {type: "exchange", option: null};

        const container = document.getElementById("exchange-options");
        container.replaceChildren();
        cfg.exchangeOptions.forEach((option) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "exchange-btn";
            btn.appendChild(pieceImage(option.rescue, ""));
            btn.appendChild(pieceImage(option.payment, ""));

            const label = document.createElement("span");
            label.className = "exchange-label";
            label.textContent = `Rescue your ${pieceName(option.rescue)}, pay a ${pieceName(option.payment)}`;
            btn.appendChild(label);

            btn.addEventListener("click", () => chooseExchange(option));
            container.appendChild(btn);
        });

        updateControls();
        exchangeDialog.showModal();
    }

    function chooseExchange(option) {
        mode.option = option;
        exchangeDialog.close();
        highlightSquares(option.validDrops, "highlight-drop");
        setStatus(`Click a highlighted square to place your ${pieceName(option.rescue)}`);
    }

    // Handles clicks on the board while a drop or exchange is waiting for a square.
    function onBoardClick(e) {
        if (mode === null) return;
        const square = e.target.closest("[data-square]")?.getAttribute("data-square");
        if (!square) return;

        if (mode.type === "drop") {
            const {airfieldIdx} = mode;
            const legal = cfg.dropMoves.some((drop) => drop.airfieldIdx === airfieldIdx && drop.to === square);
            if (legal) {
                cancelMode();
                submitAction("/api/drop", {airfield_idx: airfieldIdx, to: square});
            }
        } else if (mode.option?.validDrops.includes(square)) {
            const {option} = mode;
            cancelMode();
            submitAction("/api/exchange", {
                rescue_idx: option.rescueIdx,
                payment_idx: option.paymentIdx,
                drop_square: square,
            });
        }
    }

    // Closing the exchange dialog before picking an exchange cancels it
    function onExchangeClose() {
        if (mode?.type === "exchange" && mode.option === null) cancelMode();
    }

    // Escape cancels a drop or exchange that is waiting for a square. An open dialog
    // handles Escape itself.
    function onKeyDown(e) {
        if (e.key === "Escape" && mode !== null && !exchangeDialog.open && !promotionDialog.open) cancelMode();
    }

    // Server communication

    async function fetchJSON(url, options) {
        const response = await fetch(url, options);
        return response.json();
    }

    const postJSON = (url, data) =>
        fetchJSON(url, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data),
        });

    // Send a move, drop, exchange, or resignation for the current turn.
    async function submitAction(url, data) {
        clearInterval(timerInterval);
        try {
            const response = await postJSON(url, {...data, game_no: cfg.gameNo, turn_no: cfg.turnNo, player: cfg.player});
            if (response.game_over) {
                showGameOver();
            } else {
                // On an error the board returns to the latest saved position, with the reason shown.
                fetchAndRefresh(response.error);
            }
        } catch {
            startTimer();
            setStatus("Could not reach the server. Try again.", true);
        }
    }

    async function sendTimeout(turnNo) {
        try {
            const response = await postJSON("/api/timeout", {game_no: cfg.gameNo, turn_no: turnNo});
            if (response.game_over) {
                showGameOver();
            } else if (cfg.turnNo === turnNo) {
                // The server's clock can be a moment behind this one, so ask again shortly.
                // If the turn has changed, polling has already picked up the new position.
                setTimeout(() => sendTimeout(turnNo), 1000);
            }
        } catch {
            setTimeout(() => sendTimeout(turnNo), 2000);
        }
    }

    function showGameOver() {
        window.location.href = `/game_over?game_no=${cfg.gameNo}`;
    }

    // Load the latest turn and update the page in place. `notice` is an error to show afterwards.
    async function fetchAndRefresh(notice) {
        try {
            const data = await fetchJSON(`/api/game_data?game_no=${cfg.gameNo}&player=${cfg.player}`);
            if (data.game_over) {
                showGameOver();
            } else if (data.error) {
                setStatus(data.error, true);
            } else {
                applyView(data);
                if (notice) setStatus(notice, true);
            }
        } catch {
            setStatus("Could not reach the server. Retrying.", true);
        }
    }

    function applyView(view) {
        cfg = view;
        mode = null;
        clearHighlights();
        if (exchangeDialog.open) exchangeDialog.close();
        if (promotionDialog.open) promotionDialog.close();

        buildLegalMoveMap();
        board.position(cfg.boardFen, true);
        renderTrays();
        updateControls();
        showTurnStatus();
        startTimer();
        startPolling();
    }

    // Poll on both players' turns, so a resignation or timeout from either side is picked up.
    function startPolling() {
        clearInterval(pollInterval);
        pollInterval = setInterval(async () => {
            try {
                const data = await fetchJSON(`/api/poll?game_no=${cfg.gameNo}&turn_no=${cfg.turnNo}`);
                if (data.game_over) {
                    clearInterval(pollInterval);
                    showGameOver();
                } else if (data.update_available) {
                    clearInterval(pollInterval);
                    fetchAndRefresh();
                }
            } catch {
                // Try again on the next interval
            }
        }, POLL_INTERVAL_MS);
    }

    // Start

    $(() => {
        initBoard();
        document.getElementById("myBoard").addEventListener("click", onBoardClick, true);
        document.addEventListener("keydown", onKeyDown);

        document.getElementById("btn-drop").addEventListener("click", () => {
            if (mode?.type === "drop") {
                cancelMode();
            } else {
                toggleDrop(cfg.dropMoves[0].airfieldIdx);
            }
        });
        document.getElementById("btn-exchange").addEventListener("click", () => {
            if (mode?.type === "exchange") {
                cancelMode();
            } else {
                startExchange();
            }
        });

        exchangeDialog.addEventListener("close", onExchangeClose);
        promotionDialog.addEventListener("close", onPromotionClose);
        document.getElementById("cancel-exchange").addEventListener("click", () => exchangeDialog.close());
        document.getElementById("cancel-promotion").addEventListener("click", () => promotionDialog.close());

        document.getElementById("btn-resign").addEventListener("click", () => {
            if (confirm("Resign and forfeit the game?")) {
                submitAction("/api/resign", {});
            }
        });

        applyView(cfg);
    });
})();
