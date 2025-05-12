// scripts/deploy.js
//
// Usage: npx hardhat run --network localhost scripts/deploy.js
// Dependencies: Ensure `@nomicfoundation/hardhat-toolbox` is required in hardhat.config.js

const fs = require("fs");
const path = require("path");

async function main() {
  // Hardhat Runtime Environment injects `ethers` automatically
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with account:", deployer.address);

  // 1. Get contract factory for StringChain
  const Factory = await ethers.getContractFactory("StringChain");

  // 2. Deploy the contract
  const contract = await Factory.deploy();
  await contract.waitForDeployment();

  const addr = await contract.getAddress();
  console.log("✔ StringChain deployed to:", addr);

  // 3. Write deployed address to stringchain.addr (overwrite if exists)
  const filePath = path.resolve(__dirname, "..", "stringchain.addr");
  fs.writeFileSync(filePath, addr);
  console.log(`✔ Address written to ${filePath}`);
}

// Run the deployment script
main().catch((err) => {
  console.error(err);
  process.exit(1);
});
