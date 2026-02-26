import express from 'express';
import http from 'http';
import { Server } from 'socket.io';
import cors from 'cors';
import { createClient, createAccount } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { TransactionStatus } from 'genlayer-js/types';
import fs from 'fs';
import path from 'path';

const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS || '0x68850c902d8193fa29419e3a3a043054d416CA08';
const OPERATOR_KEY     = process.env.OPERATOR_PRIVATE_KEY || '0xa7db0893b5433f384c92669e3d54b7106e069a8d3cff415ee31affebdfa6b0bc';
const PORT             = process.env.PORT || 3001;
const STUDIO_RPC = 'https://studio.genlayer.com/api';
const LEADERBOARD_FILE = './leaderboard.json';

let USE_AI_QUESTIONS = false; // set true when AI generation succeeds on startup

const app = express();
const httpServer = http.createServer(app);
const io = new Server(httpServer, { cors: { origin: '*', methods: ['GET','POST'] } });
app.use(cors());
app.use(express.json());

let client = null;
let operatorAccount = null;
const rooms = {};
let serverRoomCounter = 0;

// ── PERSISTENT LEADERBOARD ────────────────────────────────────────────────────
// Saves to disk so it survives server restarts

function loadLeaderboard() {
  try {
    if (fs.existsSync(LEADERBOARD_FILE)) {
      const raw = fs.readFileSync(LEADERBOARD_FILE, 'utf8');
      return JSON.parse(raw);
    }
  } catch (e) {
    console.log('⚠️  Could not load leaderboard file, starting fresh.');
  }
  return {};
}

function saveLeaderboard() {
  try {
    fs.writeFileSync(LEADERBOARD_FILE, JSON.stringify(globalLeaderboard, null, 2));
  } catch (e) {
    console.log('⚠️  Could not save leaderboard:', e.message);
  }
}

let globalLeaderboard = loadLeaderboard();
console.log(`📊 Loaded leaderboard with ${Object.keys(globalLeaderboard).length} players`);

function updateLeaderboard(ranking, nicknames) {
  ranking.forEach((entry, i) => {
    const addr = entry.player;
    if (!globalLeaderboard[addr]) {
      globalLeaderboard[addr] = { nickname: nicknames[addr] || '', totalXp: 0, gamesPlayed: 0, wins: 0 };
    }
    globalLeaderboard[addr].totalXp += entry.score;
    globalLeaderboard[addr].gamesPlayed += 1;
    if (i === 0) globalLeaderboard[addr].wins += 1;
    if (nicknames[addr]) globalLeaderboard[addr].nickname = nicknames[addr];
  });
  saveLeaderboard();
  console.log('🏆 Leaderboard updated and saved to disk:', globalLeaderboard);
}

// ── 50 TRIVIA STATEMENTS WITH DIFFICULTY ─────────────────────────────────────
// difficulty: 'easy' | 'medium' | 'hard'
// speedBonus: max bonus XP for fastest correct answer (added on top of base 50)

const ALL_STATEMENTS = [
  // ── EASY (well-known facts, common myths) ───────────────────────────────────
  { statement: "The Great Wall of China is not visible from space with the naked eye.", answer: "TRUE", explanation: "Despite the myth, the wall is too narrow (~15 feet wide) to see from orbit without aid.", difficulty: "easy", speedMax: 15 },
  { statement: "Honey never expires — archaeologists found 3000-year-old honey in Egyptian tombs that was still edible.", answer: "TRUE", explanation: "Honey's low moisture and acidic pH prevent bacterial growth, making it last indefinitely if sealed.", difficulty: "easy", speedMax: 15 },
  { statement: "Octopuses have three hearts and blue blood.", answer: "TRUE", explanation: "Two hearts pump blood to the gills; one pumps to the body. Copper-based haemocyanin makes blood blue.", difficulty: "easy", speedMax: 15 },
  { statement: "The Eiffel Tower was originally built as a permanent structure for Paris.", answer: "TWIST", explanation: "It was built as a temporary exhibit for the 1889 World's Fair and was slated for demolition.", difficulty: "easy", speedMax: 15 },
  { statement: "Bananas are technically berries, but strawberries are not.", answer: "TRUE", explanation: "Botanically, bananas develop from a single flower with one ovary. Strawberries are 'accessory fruits'.", difficulty: "easy", speedMax: 15 },
  { statement: "Lightning never strikes the same place twice.", answer: "TWIST", explanation: "Lightning frequently strikes the same place multiple times — the Empire State Building is hit ~20–25 times per year.", difficulty: "easy", speedMax: 15 },
  { statement: "Humans have five senses.", answer: "TWIST", explanation: "Humans have at least 9 senses including proprioception, thermoception, nociception, and the vestibular sense.", difficulty: "easy", speedMax: 15 },
  { statement: "Goldfish have a memory span of only 3 seconds.", answer: "TWIST", explanation: "Studies show goldfish can remember things for months and can be trained to perform tasks.", difficulty: "easy", speedMax: 15 },
  { statement: "Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid.", answer: "TRUE", explanation: "The pyramids were built ~2560 BC; Cleopatra lived ~30 BC; the Moon landing was 1969 AD.", difficulty: "easy", speedMax: 15 },
  { statement: "A day on Venus is shorter than a year on Venus.", answer: "TWIST", explanation: "A Venus day (243 Earth days) is actually LONGER than its year (225 Earth days).", difficulty: "easy", speedMax: 15 },

  // ── MEDIUM (less obvious, needs knowledge) ───────────────────────────────────
  { statement: "Mount Everest is the tallest mountain on Earth measured from its base.", answer: "TWIST", explanation: "Mauna Kea is taller from base to peak (~10,210m), but most of it is underwater. Everest wins by sea-level height.", difficulty: "medium", speedMax: 20 },
  { statement: "The human brain uses about 20% of the body's total energy.", answer: "TRUE", explanation: "The brain is only 2% of body weight but consumes ~20% of total caloric energy.", difficulty: "medium", speedMax: 20 },
  { statement: "Lightning strikes the Earth about 100 times every second.", answer: "TRUE", explanation: "Earth experiences roughly 8 million lightning strikes per day — about 100 per second.", difficulty: "medium", speedMax: 20 },
  { statement: "Water always boils at 100°C (212°F).", answer: "TWIST", explanation: "Boiling point varies with altitude and pressure. At the top of Everest, water boils at ~70°C.", difficulty: "medium", speedMax: 20 },
  { statement: "Napoleon Bonaparte was unusually short for his era.", answer: "TWIST", explanation: "Napoleon was ~5'7\" (170cm) — average to tall for the time. The 'short Napoleon' myth stemmed from British propaganda.", difficulty: "medium", speedMax: 20 },
  { statement: "Sharks are the only fish that cannot blink.", answer: "TWIST", explanation: "Most fish don't have eyelids. Some sharks do have a nictitating membrane — a protective third eyelid.", difficulty: "medium", speedMax: 20 },
  { statement: "The Amazon River flows into the Atlantic Ocean.", answer: "TRUE", explanation: "The Amazon discharges into the Atlantic near Marajó Island in Brazil, pushing freshwater 160km into the ocean.", difficulty: "medium", speedMax: 20 },
  { statement: "Oxford University is older than the Aztec Empire.", answer: "TRUE", explanation: "Oxford started teaching around 1096–1167. The Aztec Empire was founded in 1428.", difficulty: "medium", speedMax: 20 },
  { statement: "Diamonds are the hardest natural substance on Earth.", answer: "TRUE", explanation: "Diamonds score 10 on the Mohs scale — the maximum. Nothing natural scratches a diamond.", difficulty: "medium", speedMax: 20 },
  { statement: "The tongue has different zones for detecting different tastes.", answer: "TWIST", explanation: "The 'tongue map' is a myth. All taste buds can detect all five basic tastes across the entire tongue.", difficulty: "medium", speedMax: 20 },
  { statement: "Sound travels faster through water than through air.", answer: "TRUE", explanation: "Sound travels ~1480 m/s in water vs ~343 m/s in air because water molecules are more tightly packed.", difficulty: "medium", speedMax: 20 },
  { statement: "A group of flamingos is called a flamboyance.", answer: "TRUE", explanation: "Flamingo groups are officially called a flamboyance, pat, colony, or stand.", difficulty: "medium", speedMax: 20 },
  { statement: "The Great Fire of London in 1666 killed thousands of people.", answer: "TWIST", explanation: "Remarkably, only 6 deaths were officially recorded in the Great Fire of London despite 13,000 homes destroyed.", difficulty: "medium", speedMax: 20 },
  { statement: "Glass is a liquid that flows very slowly over time.", answer: "TWIST", explanation: "Glass is an amorphous solid. Old windows are thicker at the bottom due to manufacturing techniques, not flow.", difficulty: "medium", speedMax: 20 },
  { statement: "Butterflies taste with their feet.", answer: "TRUE", explanation: "Butterflies have taste sensors on their tarsi (feet) to identify plants for egg-laying and food.", difficulty: "medium", speedMax: 20 },
  { statement: "The human body contains about 37 trillion cells.", answer: "TRUE", explanation: "Current estimates put human cell count at 37 trillion, with red blood cells being the most numerous.", difficulty: "medium", speedMax: 20 },
  { statement: "Walt Disney was the first voice of Mickey Mouse.", answer: "TRUE", explanation: "Walt Disney voiced Mickey Mouse from 1928 until 1947 when he handed the role to Jim Macdonald.", difficulty: "medium", speedMax: 20 },
  { statement: "All planets in our solar system rotate in the same direction.", answer: "TWIST", explanation: "Venus rotates clockwise (retrograde), and Uranus rotates on its side. Most others rotate counterclockwise.", difficulty: "medium", speedMax: 20 },

  // ── HARD (counterintuitive, niche knowledge) ─────────────────────────────────
  { statement: "Cats can't taste sweetness.", answer: "TRUE", explanation: "Cats lack the Tas1r2 gene required to detect sweet flavours — they have no functional sweet taste receptor.", difficulty: "hard", speedMax: 25 },
  { statement: "The word 'set' has the most definitions of any word in the English dictionary.", answer: "TRUE", explanation: "In the Oxford English Dictionary, 'set' has 430+ definitions — more than any other word.", difficulty: "hard", speedMax: 25 },
  { statement: "The Sahara Desert has always been a desert.", answer: "TWIST", explanation: "Around 6,000–11,000 years ago the Sahara was green and had lakes, rivers, and hippos. This is called the 'Green Sahara'.", difficulty: "hard", speedMax: 25 },
  { statement: "You cannot hum while holding your nose closed.", answer: "TRUE", explanation: "Humming requires air to escape through the nose. Pinch your nose and the hum stops.", difficulty: "hard", speedMax: 25 },
  { statement: "The first computer bug was an actual bug.", answer: "TRUE", explanation: "In 1947, Grace Hopper's team found a moth in a Harvard Mark II relay — the first literal computer bug.", difficulty: "hard", speedMax: 25 },
  { statement: "Hot water freezes faster than cold water.", answer: "TRUE", explanation: "This is the Mpemba effect. Under certain conditions hot water does freeze faster, though scientists still debate the mechanism.", difficulty: "hard", speedMax: 25 },
  { statement: "Wombat droppings are cube-shaped.", answer: "TRUE", explanation: "Wombats produce cube-shaped scat due to the last 8% of their intestine stretching at different rates. Unique in the animal kingdom.", difficulty: "hard", speedMax: 25 },
  { statement: "The shortest war in history lasted 38 minutes.", answer: "TRUE", explanation: "The Anglo-Zanzibar War of 1896 lasted between 38 and 45 minutes — the shortest war ever recorded.", difficulty: "hard", speedMax: 25 },
  { statement: "Humans share about 50% of their DNA with bananas.", answer: "TRUE", explanation: "Approximately 50% of human genes are shared with bananas due to common cellular machinery inherited from a common ancestor.", difficulty: "hard", speedMax: 25 },
  { statement: "Pluto is smaller than the United States.", answer: "TRUE", explanation: "Pluto's surface area (~17.6M km²) is smaller than Russia, and about 1.5× the size of the contiguous US.", difficulty: "hard", speedMax: 25 },
  { statement: "A single strand of spaghetti is called a spaghetto.", answer: "TRUE", explanation: "Grammatically correct Italian singular of 'spaghetti' (plural) is 'spaghetto'. Same logic applies to panino/panini.", difficulty: "hard", speedMax: 25 },
  { statement: "There are more possible chess games than atoms in the observable universe.", answer: "TRUE", explanation: "The Shannon number estimates 10^120 possible chess games vs ~10^80 atoms in the observable universe.", difficulty: "hard", speedMax: 25 },
  { statement: "Humans are the only animals that cook their food.", answer: "TRUE", explanation: "No other animal deliberately applies heat to transform food. Cooking is considered a key driver of human brain evolution.", difficulty: "hard", speedMax: 25 },
  { statement: "The inventor of the World Wide Web invented it in the USA.", answer: "TWIST", explanation: "Tim Berners-Lee invented the WWW in 1989 while working at CERN in Geneva, Switzerland.", difficulty: "hard", speedMax: 25 },
  { statement: "Crows can recognise and remember human faces.", answer: "TRUE", explanation: "Studies show crows can recognise individual humans, hold grudges, and even warn other crows about 'dangerous' faces.", difficulty: "hard", speedMax: 25 },
  { statement: "A day on Mercury is longer than a year on Mercury.", answer: "TRUE", explanation: "Mercury rotates so slowly that one solar day (176 Earth days) is longer than its orbital year (88 Earth days).", difficulty: "hard", speedMax: 25 },
  { statement: "The average human walks about 100,000 miles in a lifetime.", answer: "TRUE", explanation: "Averaging ~7,500 steps/day over a lifetime, most people walk about 100,000 miles — equivalent to 4 trips around Earth.", difficulty: "hard", speedMax: 25 },
  { statement: "There are more trees on Earth than stars in the Milky Way.", answer: "TRUE", explanation: "Earth has ~3 trillion trees; the Milky Way has an estimated 100–400 billion stars.", difficulty: "hard", speedMax: 25 },
  { statement: "Helium was first discovered on Earth before it was discovered in space.", answer: "TWIST", explanation: "Helium was discovered in the sun's spectrum in 1868 (hence 'helios') before being found on Earth in 1895.", difficulty: "hard", speedMax: 25 },
  { statement: "A teaspoon of a neutron star would weigh about 10 million tons.", answer: "TRUE", explanation: "Neutron stars have densities of ~4×10^17 kg/m³. A teaspoon (~5mL) would weigh roughly 10 million metric tons on Earth.", difficulty: "hard", speedMax: 25 },
  { statement: "The letter 'E' appears in the US Declaration of Independence more than any other letter.", answer: "TRUE", explanation: "'E' is the most common letter in English. In the Declaration, 'e' appears over 1,300 times.", difficulty: "hard", speedMax: 25 },
];

// Per-room statement indices
const roomStatements = {};

function pickStatementsForRoom(roomId, difficulty = 'mixed') {
  const n = ALL_STATEMENTS.length;
  // For mixed: pick 2 easy, 2 medium, 1 hard (5 total)
  // For specific difficulty: pick 5 from that tier
  let pool;
  if (difficulty === 'easy') {
    pool = ALL_STATEMENTS.filter(s => s.difficulty === 'easy');
  } else if (difficulty === 'medium') {
    pool = ALL_STATEMENTS.filter(s => s.difficulty === 'medium');
  } else if (difficulty === 'hard') {
    pool = ALL_STATEMENTS.filter(s => s.difficulty === 'hard');
  } else {
    // mixed: 2 easy + 2 medium + 1 hard
    const easy   = shuffle(ALL_STATEMENTS.filter(s => s.difficulty === 'easy')).slice(0, 2);
    const medium = shuffle(ALL_STATEMENTS.filter(s => s.difficulty === 'medium')).slice(0, 2);
    const hard   = shuffle(ALL_STATEMENTS.filter(s => s.difficulty === 'hard')).slice(0, 1);
    pool = [...easy, ...medium, ...hard];
    // shuffle the final 5 so order is random
    return shuffle(pool).map(s => ALL_STATEMENTS.indexOf(s));
  }
  return shuffle(pool).slice(0, 5).map(s => ALL_STATEMENTS.indexOf(s));
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function getStatementForRoom(roomId, round) {
  const indices = roomStatements[roomId];
  if (!indices) return null;
  const idx = indices[(round - 1) % indices.length];
  return ALL_STATEMENTS[idx] || null;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── CONNECT ───────────────────────────────────────────────────────────────────
async function initializeClient() {
  try {
    console.log('Connecting to GenLayer Studio...');
    operatorAccount = createAccount(OPERATOR_KEY);
    client = createClient({ chain: studionet, account: operatorAccount });
    await client.initializeConsensusSmartContract();
    console.log('✅ Connected! Operator:', operatorAccount.address);
    return true;
  } catch (err) {
    console.error('❌ Connection failed:', err.message);
    return false;
  }
}

async function recreateClient() {
  try {
    client = createClient({ chain: studionet, account: operatorAccount });
    await client.initializeConsensusSmartContract();
    console.log('✅ Reconnected!');
  } catch(e) { console.error('Reconnect failed:', e.message); }
}

// ── RPC ───────────────────────────────────────────────────────────────────────
async function readContractDirect(functionName, args = []) {
  try {
    const payload = {
      jsonrpc: '2.0', method: 'gen_call',
      params: [{ to: CONTRACT_ADDRESS, data: { method: functionName, args }, state_status: 'accepted' }],
      id: Date.now(),
    };
    const res  = await fetch(STUDIO_RPC, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const json = await res.json();
    if (json.error) throw new Error(json.error.message || JSON.stringify(json.error));
    const raw = json.result;
    if (!raw) return null;
    if (typeof raw === 'object') return raw;
    if (typeof raw === 'string' && raw.startsWith('0x')) {
      try {
        const decoded = Buffer.from(raw.slice(2), 'hex').toString('utf8');
        try { return JSON.parse(decoded); } catch(e) { return decoded; }
      } catch(e) {}
    }
    return raw;
  } catch (err) {
    console.log(`Direct RPC read failed for ${functionName}: ${err.message.slice(0,80)}`);
    throw err;
  }
}

async function readContract(functionName, args = []) {
  try { return await readContractDirect(functionName, args); } catch(err) {
    console.log(`Direct read failed, trying SDK... (${err.message.slice(0,60)})`);
  }
  try {
    return await client.readContract({ address: CONTRACT_ADDRESS, functionName, args, stateStatus: 'accepted' });
  } catch (err) { throw err; }
}

async function writeContractLeaderOnly(functionName, args = []) {
  console.log(`📝 Calling (leader only): ${functionName}`);
  const txHash = await client.writeContract({ address: CONTRACT_ADDRESS, functionName, args, value: 0n, leaderOnly: true });
  console.log('⏳ Waiting for leader only tx:', txHash);
  const receipt = await client.waitForTransactionReceipt({ hash: txHash, status: TransactionStatus.ACCEPTED, retries: 30, interval: 3000 });
  console.log('✅ Done (leader only):', functionName);
  return receipt;
}

async function writeContract(functionName, args = []) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      console.log(`📝 Calling: ${functionName} (attempt ${attempt})`);
      const txHash = await client.writeContract({ address: CONTRACT_ADDRESS, functionName, args, value: 0n });
      console.log('⏳ Waiting for consensus... tx:', txHash);
      const receipt = await client.waitForTransactionReceipt({ hash: txHash, status: TransactionStatus.ACCEPTED, retries: 60, interval: 5000 });
      console.log('✅ Done:', functionName);
      return receipt;
    } catch (err) {
      const msg = err.message || '';
      console.log(`Write attempt ${attempt} failed: ${msg.slice(0,100)}`);
      if (attempt < 3) {
        await sleep(5000);
        if (msg.includes('fetch failed') || msg.includes('unknown RPC') || msg.includes('Unknown')) await recreateClient();
      } else throw err;
    }
  }
}

// ── HTTP ROUTES ───────────────────────────────────────────────────────────────
app.get('/health', (req, res) => res.json({ status:'alive', contract: CONTRACT_ADDRESS, network:'studionet', questions: ALL_STATEMENTS.length }));

app.get('/api/weekly-topic', async (req, res) => {
  try {
    const data = await readContract('get_weekly_topic', []);
    res.json({ success: true, data });
  } catch (err) {
    res.json({ success: true, data: { topic: 'Mixed Trivia · 50 Questions', statements_ready: true } });
  }
});

app.get('/api/leaderboard', async (req, res) => {
  const lb = Object.entries(globalLeaderboard)
    .map(([addr, d]) => ({ player: addr, nickname: d.nickname, totalXp: d.totalXp, gamesPlayed: d.gamesPlayed, wins: d.wins }))
    .sort((a,b) => b.totalXp - a.totalXp)
    .slice(0, 20);
  res.json({ success: true, data: lb });
});

app.get('/api/room/:roomId', async (req, res) => {
  try {
    const data = await readContract('get_room_state', [req.params.roomId]);
    res.json({ success: true, data });
  } catch (err) { res.status(500).json({ success: false, error: err.message }); }
});

app.get('/api/player-profile/:address', async (req, res) => {
  try {
    const data = await readContract('get_player_profile', [req.params.address]);
    res.json({ success: true, data });
  } catch (err) {
    res.json({ success: true, data: { address: req.params.address, registered: false, total_xp: 0, games_played: 0, wins: 0 } });
  }
});

app.get('/api/on-chain-leaderboard', async (req, res) => {
  try {
    const data = await readContract('get_leaderboard', []);
    res.json({ success: true, data, source: 'chain' });
  } catch (err) {
    // Fallback to server memory
    const lb = Object.entries(globalLeaderboard)
      .map(([addr, d]) => ({ player: addr, nickname: d.nickname, totalXp: d.totalXp, gamesPlayed: d.gamesPlayed, wins: d.wins }))
      .sort((a,b) => b.totalXp - a.totalXp).slice(0, 20);
    res.json({ success: true, data: lb, source: 'memory' });
  }
});

app.get('/api/weekly-questions', async (req, res) => {
  try {
    const data = await readContract('get_weekly_questions', []);
    res.json({ success: true, data, source: 'chain' });
  } catch (err) {
    res.json({ success: false, error: err.message });
  }
});

app.get('/api/statements', (req, res) => {
  res.json({ 
    total: ALL_STATEMENTS.length,
    byDifficulty: {
      easy:   ALL_STATEMENTS.filter(s=>s.difficulty==='easy').length,
      medium: ALL_STATEMENTS.filter(s=>s.difficulty==='medium').length,
      hard:   ALL_STATEMENTS.filter(s=>s.difficulty==='hard').length,
    }
  });
});

// ── SOCKET.IO ─────────────────────────────────────────────────────────────────
io.on('connection', (socket) => {
  console.log('🟢 Player connected:', socket.id);

  socket.on('disconnect', () => {
    const roomId = socket.currentRoom;
    if (!roomId || !rooms[roomId]) return;
    rooms[roomId].sockets = rooms[roomId].sockets.filter(id => id !== socket.id);
    const addr = rooms[roomId].players[socket.id];
    delete rooms[roomId].players[socket.id];

    // Handle spectators
    if (rooms[roomId].spectators) {
      rooms[roomId].spectators = rooms[roomId].spectators.filter(id => id !== socket.id);
    }

    if (rooms[roomId].sockets.length === 0) {
      delete rooms[roomId];
    } else {
      const nick = rooms[roomId].nicknames?.[addr] || addr?.slice(0,6) || 'Player';
      io.to(roomId).emit('player_left', { message: nick + ' disconnected' });
    }
  });

  // CREATE ROOM
  socket.on('create_room', async (data) => {
    try {
      const { playerAddress, difficulty = 'mixed' } = data;
      socket.emit('status_update', { message: '⛓️ Creating room...' });

      // Register player profile on-chain (creates profile + proves wallet activity)
      try {
        await writeContractLeaderOnly('register_player', [playerAddress, data.nickname || '']);
        console.log('👤 Player registered on-chain:', playerAddress.slice(0,10));
      } catch(e) {
        console.log('⚠️  register_player failed (non-critical):', e.message.slice(0,60));
      }

      const receipt = await writeContractLeaderOnly('create_room', [playerAddress]);

      let roomId = null;
      try {
        const stdout = receipt?.consensus_data?.leader_receipt?.[0]?.genvm_result?.stdout;
        if (typeof stdout === 'string' && stdout.trim().startsWith('ROOM')) roomId = stdout.trim();
      } catch(e) {}

      if (!roomId) {
        serverRoomCounter++;
        roomId = 'ROOM-' + String(serverRoomCounter).padStart(4, '0');
        console.log('⚠️ Using server counter fallback:', roomId);
      }

      const nickname = data.nickname || '';
      rooms[roomId] = {
        sockets:    [socket.id],
        players:    { [socket.id]: playerAddress },
        spectators: [],
        nicknames:  { [playerAddress]: nickname },
        host:       socket.id,
        currentRound: 1,
        submissions:  {},
        scores:       {},
        difficulty,
        gameActive: false,
      };

      // Pick 5 random statements based on difficulty
      const indices = pickStatementsForRoom(roomId, difficulty);
      roomStatements[roomId] = indices;
      console.log('📚 Room', roomId, `[${difficulty}]`, 'statements:', indices.map(i => ALL_STATEMENTS[i].statement.slice(0,30)));

      socket.join(roomId);
      socket.currentRoom = roomId;
      socket.playerAddress = playerAddress;
      socket.isSpectator = false;

      socket.emit('room_created', {
        success: true, roomId, isHost: true,
        difficulty,
        roomState: {
          room_id: roomId, players: [playerAddress], player_count: 1,
          host: playerAddress, nicknames: rooms[roomId].nicknames,
          status: 'waiting', difficulty,
        }
      });
      console.log('🏠 Room ready:', roomId, `[${difficulty}]`);

    } catch (err) {
      console.error('create_room error:', err.message);
      socket.emit('error', { message: 'Failed to create room. (' + err.message.slice(0,60) + ')' });
    }
  });

  // JOIN ROOM (or spectate if game already active)
  socket.on('join_room', async (data) => {
    try {
      const { roomId, playerAddress } = data;
      if (!rooms[roomId]) {
        socket.emit('error', { message: 'Room ' + roomId + ' not found!' });
        return;
      }

      const room = rooms[roomId];

      // If game is active → join as spectator
      if (room.gameActive) {
        room.spectators = room.spectators || [];
        room.spectators.push(socket.id);
        socket.join(roomId);
        socket.currentRoom = roomId;
        socket.playerAddress = playerAddress;
        socket.isSpectator = true;

        const joinNick = data.nickname || '';
        room.nicknames[playerAddress] = joinNick;

        socket.emit('joined_as_spectator', {
          roomId,
          message: '👁️ Game in progress — you are spectating!',
          roomState: {
            room_id: roomId,
            players: Object.values(room.players),
            scores: room.scores || {},
            current_round: room.currentRound,
            nicknames: room.nicknames,
            status: 'active',
          }
        });
        console.log('👁️ Spectator joined:', roomId, playerAddress.slice(0,8));
        return;
      }

      socket.emit('status_update', { message: '⛓️ Joining on blockchain...' });
      // Register/update player profile on-chain
      try {
        await writeContractLeaderOnly('register_player', [playerAddress, data.nickname || '']);
      } catch(e) {
        console.log('⚠️  register_player failed (join, non-critical):', e.message.slice(0,60));
      }
      await writeContractLeaderOnly('join_room', [roomId, playerAddress]);

      room.sockets.push(socket.id);
      room.players[socket.id] = playerAddress;
      const joinNick = data.nickname || '';
      room.nicknames[playerAddress] = joinNick;
      socket.join(roomId);
      socket.currentRoom = roomId;
      socket.playerAddress = playerAddress;
      socket.isSpectator = false;

      const playerList = Object.values(room.players);
      const localRoomState = {
        room_id: roomId, players: playerList, player_count: playerList.length,
        host: room.players[room.host], nicknames: room.nicknames, status: 'waiting',
        difficulty: room.difficulty || 'mixed',
      };

      const displayMsg = joinNick || playerAddress.slice(0,6) + '...' + playerAddress.slice(-4);
      socket.emit('room_joined', { success: true, roomId, isHost: false, nicknames: room.nicknames });
      io.to(roomId).emit('room_update', { type: 'player_joined', roomId, roomState: localRoomState, message: displayMsg + ' joined!' });

    } catch (err) {
      console.error('join_room error:', err.message);
      socket.emit('error', { message: 'Failed to join: ' + err.message.slice(0,80) });
    }
  });

  // START GAME
  socket.on('start_game', async (data) => {
    try {
      const { roomId, hostAddress } = data;
      socket.emit('status_update', { message: '🚀 Starting game...' });
      const receipt = await writeContractLeaderOnly('start_game', [roomId, hostAddress]);

      const receiptStr = JSON.stringify(receipt, null, 2);
      console.log('📋 start_game FULL receipt (first 4000 chars):');
      console.log(receiptStr.slice(0, 4000));

      if (rooms[roomId]) rooms[roomId].gameActive = true;

      const stmt1 = getStatementForRoom(roomId, 1);
      const diff  = stmt1?.difficulty || 'medium';
      console.log('📋 Serving statement for round 1:', stmt1?.statement?.slice(0, 60));

      io.to(roomId).emit('game_started', { roomId });
      setTimeout(() => {
        io.to(roomId).emit('round_start', {
          round: 1, total_rounds: 5,
          statement: stmt1?.statement || 'Loading...',
          difficulty: diff,
          time_limit: 15,
        });
      }, 2000);

    } catch (err) {
      console.error('start_game error:', err.message);
      socket.emit('error', { message: 'Failed to start: ' + err.message.slice(0,80) });
    }
  });

  // SUBMIT ANSWER (with speed bonus)
  socket.on('submit_answer', async (data) => {
    try {
      const { roomId, playerAddress, answer, explanation, elapsedSeconds = 15 } = data;

      // Spectators cannot submit
      if (socket.isSpectator) return;

      const submissionTime = Math.floor(Date.now() / 1000);
      await writeContractLeaderOnly('submit_answer', [roomId, playerAddress, answer, explanation || '', submissionTime]);
      socket.emit('answer_received', { success: true });

      if (!rooms[roomId].submissions) rooms[roomId].submissions = {};
      rooms[roomId].submissions[playerAddress] = { answer, explanation: explanation || '', elapsedSeconds };

      const submitted = Object.keys(rooms[roomId].submissions).length;
      const total     = Object.keys(rooms[roomId].players).length;
      console.log(`📊 Submissions: ${submitted}/${total} for ${roomId}`);

      io.to(roomId).emit('submission_update', { submitted_count: submitted, total_players: total, waiting_for: total - submitted });

      if (submitted >= total && total > 0) {
        console.log('🎯 All players submitted! Triggering scoring...');
        setTimeout(() => triggerScoring(roomId), 1500);
      }
    } catch (err) {
      console.error('submit_answer error:', err.message);
      socket.emit('error', { message: 'Failed to submit: ' + err.message.slice(0,80) });
    }
  });
});

// ── SCORING (server-side with speed bonus) ────────────────────────────────────
async function triggerScoring(roomId) {
  try {
    io.to(roomId).emit('scoring_in_progress', { message: '⚡ Scoring your answers...' });

    try { await writeContractLeaderOnly('score_round', [roomId]); } catch(e) {}

    if (!rooms[roomId]) { console.error('Room gone:', roomId); return; }
    const currentRound = rooms[roomId].currentRound || 1;
    const stmt = getStatementForRoom(roomId, currentRound);
    const correctAnswer = stmt?.answer || 'TRUE';
    const correctExplanation = stmt?.explanation || '';
    const speedMax = stmt?.speedMax || 15; // max speed bonus XP for this question

    const submissions = rooms[roomId].submissions || {};
    const roundResults = {};

    for (const [addr, sub] of Object.entries(submissions)) {
      const gotCorrect = sub.answer === correctAnswer;
      const baseXp = gotCorrect ? 50 : 0;

      // Speed bonus: faster = more XP (only awarded for correct answers)
      // elapsedSeconds=0 → full speedMax bonus, elapsedSeconds=15 → 0 bonus
      let speedBonus = 0;
      if (gotCorrect) {
        const elapsed = Math.min(15, sub.elapsedSeconds || 15);
        speedBonus = Math.round(speedMax * (1 - elapsed / 15));
      }

      const totalXp = baseXp + speedBonus;
      if (!rooms[roomId].scores) rooms[roomId].scores = {};
      rooms[roomId].scores[addr] = (rooms[roomId].scores[addr] || 0) + totalXp;

      roundResults[addr] = {
        correct: gotCorrect,
        answer: sub.answer,
        round_xp: totalXp,
        base_xp: baseXp,
        speed_bonus: speedBonus,
        elapsed_seconds: sub.elapsedSeconds || 15,
      };
    }

    const scores = rooms[roomId].scores || {};
    console.log(`📊 Round ${currentRound} scores:`, scores);

    const roundResult = {
      correct_answer: correctAnswer,
      real_explanation: correctExplanation,
      round_results: roundResults,
      difficulty: stmt?.difficulty || 'medium',
    };

    const nextRound = currentRound + 1;
    rooms[roomId].submissions = {};
    rooms[roomId].currentRound = nextRound;
    const isLastRound = currentRound >= 5;

    console.log('📊 Emitting round_results. scores:', JSON.stringify(scores));
    const nicknames = rooms[roomId]?.nicknames || {};
    io.to(roomId).emit('round_results', {
      roundResult,
      roomState: { scores, nicknames, current_round: nextRound, status: isLastRound ? 'finished' : 'active' }
    });

    if (isLastRound) {
      rooms[roomId].gameActive = false;
      const finalScores = rooms[roomId].scores || {};
      const ranking = Object.entries(finalScores)
        .sort((a,b) => b[1]-a[1])
        .map(([player, score], i) => ({ rank: i+1, player, score }));
      console.log('🏆 Game over! Ranking:', ranking);
      const gameNicknames = rooms[roomId]?.nicknames || {};
      updateLeaderboard(ranking, gameNicknames);

      // Update on-chain player profiles (async, non-blocking)
      Promise.allSettled(ranking.map(async (entry) => {
        try {
          await writeContractLeaderOnly('update_player_stats', [
            entry.player,
            entry.score,
            entry.rank === 1,
            entry.score,
          ]);
          console.log(`👤 On-chain profile updated: ${entry.player.slice(0,10)} +${entry.score}XP`);
        } catch(e) {
          console.log('⚠️  update_player_stats failed (non-critical):', e.message.slice(0,60));
        }
      })).then(() => console.log('✅ All on-chain profiles updated'));

      io.to(roomId).emit('game_over', { final_ranking: ranking, nicknames: gameNicknames });
    } else {
      setTimeout(() => {
        const nextStmt = getStatementForRoom(roomId, nextRound);
        console.log('📋 Round', nextRound, 'statement:', nextStmt?.statement?.slice(0, 50));
        io.to(roomId).emit('round_start', {
          round: nextRound, total_rounds: 5,
          statement: nextStmt?.statement || 'Loading...',
          difficulty: nextStmt?.difficulty || 'medium',
          time_limit: 15,
        });
      }, 6000);
    }
  } catch (err) {
    console.error('Scoring failed:', err.message);
    io.to(roomId).emit('error', { message: 'Scoring error: ' + err.message.slice(0,80) });
  }
}

// ── START ─────────────────────────────────────────────────────────────────────
async function main() {
  const ok = await initializeClient();
  if (!ok) { process.exit(1); }
  httpServer.listen(PORT, async () => {
    console.log('\n✅ Server running! http://localhost:' + PORT + '/health\n');
    console.log('📌 Contract:', CONTRACT_ADDRESS);
    console.log('📚 Questions loaded:', ALL_STATEMENTS.length, '(Easy:', ALL_STATEMENTS.filter(s=>s.difficulty==='easy').length, '| Medium:', ALL_STATEMENTS.filter(s=>s.difficulty==='medium').length, '| Hard:', ALL_STATEMENTS.filter(s=>s.difficulty==='hard').length + ')');
    console.log('💡 Keep studio.genlayer.com open in a browser tab!\n');

    // Try AI question generation first, fall back to hardcoded if it fails
    console.log('🤖 Generating AI weekly questions (leader only, ~60s)...');
    try {
      const aiResult = await writeContractLeaderOnly('generate_ai_questions', []);
      // Parse result from receipt stdout
      let aiData = null;
      try {
        const stdout = aiResult?.consensus_data?.leader_receipt?.[0]?.genvm_result?.stdout;
        if (stdout) aiData = JSON.parse(stdout.trim());
      } catch(e) {}
      if (aiData?.questions_generated > 0) {
        console.log(`✅ AI generated ${aiData.questions_generated} questions on topic: "${aiData.topic}" 🎮`);
        USE_AI_QUESTIONS = true;
      } else {
        throw new Error('AI returned 0 questions');
      }
    } catch(e) {
      console.log('⚠️  AI generation failed, using server-side questions:', e.message.slice(0,80));
      console.log('📚 Calling fallback generate_statements...');
      try {
        await writeContractLeaderOnly('generate_statements', []);
        console.log('✅ Fallback questions ready! 🎮');
      } catch(e2) {
        console.log('⚠️  Both generation methods failed. Gameplay will use server-side questions only.');
      }
    }
  });
}

main();
